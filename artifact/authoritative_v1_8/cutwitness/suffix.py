"""Characterization-suffix synthesis W_T(a) for exposed operators (Lemma D families)."""
from __future__ import annotations
from typing import List, Tuple
from .model import Txn, ZSet, apply_txn, legal_state, state_digest
from .refmodel import Distinct, GroupAgg, Join, Project, Scan, TopK, Filter, linear_source


class SuffixUnsupported(Exception):
    pass


def source_col_map(node) -> List[int]:
    """Output column j of a linear subtree -> source table column index."""
    if isinstance(node, Scan):
        return list(range(node.arity))
    if isinstance(node, Filter):
        return source_col_map(node.child)
    if isinstance(node, Project):
        inner = source_col_map(node.child)
        return [inner[i] for i in node.cols]
    raise SuffixUnsupported("non-linear subtree")


def op_key(op, y, side=None):
    if isinstance(op, GroupAgg):
        return tuple(y[i] for i in op.gcols)
    if isinstance(op, Distinct):
        return y
    if isinstance(op, TopK):
        return tuple(y[i] for i in op.pcols)
    if isinstance(op, Join):
        return y[op.lk] if side == "L" else y[op.rk]
    raise SuffixUnsupported(type(op).__name__)


def child_for(op, side):
    if isinstance(op, Join):
        return op.left if side == "L" else op.right
    return op.child


def rows_at_key(view, x, key, side=None) -> List[Tuple[tuple, int, tuple]]:
    op = view.top
    ls = linear_source(child_for(op, side))
    if ls is None:
        raise SuffixUnsupported("operator input is not a linear single-table subtree")
    table, f = ls
    out = []
    for r, m in x[table].items_sorted():
        y = f(r)
        if y is not None and op_key(op, y, side) == key:
            out.append((r, m, y))
    return out


def delete_txn(schema, x, table, row) -> Txn:
    """Delete one copy of row, cascading to rows that reference it through foreign keys."""
    d = {table: ZSet([(row, -1)])}
    stack = [(table, row)]
    while stack:
        t, r = stack.pop()
        for child, cols, pcols in schema.children_of(t):
            key = tuple(r[i] for i in pcols)
            for cr, cm in x[child].items_sorted():
                if tuple(cr[i] for i in cols) == key and d.get(child, ZSet()).d.get(cr, 0) > -cm:
                    d.setdefault(child, ZSet()).add_row(cr, -cm)
                    stack.append((child, cr))
    return Txn(d)


def fresh_row(schema, x, table, template, set_cols=None):
    tb = schema.tables[table]
    r = list(template)
    for i, v in (set_cols or {}).items():
        r[i] = v
    if tb.pk is not None:
        for i in tb.pk:
            used = [rr[i] for rr in x[table].d if isinstance(rr[i], int)]
            if tb.cols[i][1] == "int":
                r[i] = (max(used) + 1) if used else 1
            else:
                r[i] = f"probe{len(x[table].d) + 1}"
    return tuple(r)


def key_template(schema, x, table, op, key):
    """Source row mapping to `key` through the operator's linear input subtree (for empty/dead keys).
    Tries every existing row of the table, then typed default rows, until one passes the subtree filter."""
    from decimal import Decimal
    tb = schema.tables[table]
    cmap = source_col_map(op.child)
    kout = op.gcols if isinstance(op, GroupAgg) else list(range(op.child.arity))
    kvals = key if isinstance(key, tuple) else (key,)
    cands = sorted(x[table].d, key=repr)
    palette = {"int": [1, 2, 0, -1], "dec": [Decimal("1"), Decimal("2"), Decimal("0"), Decimal("-1")], "text": ["a", "b"]}
    for j in range(4):
        row = []
        for i, (_, t, nl) in enumerate(tb.cols):
            fk = next(((c, p, pc) for c, p, pc in tb.fks if i in c), None)
            if fk is not None:
                c, p, pc = fk; parents = sorted(x[p].d, key=repr)
                row.append(parents[0][pc[c.index(i)]] if parents else None); continue
            pal = palette[t]; row.append(pal[j % len(pal)])
        cands.append(tuple(row))
    f = linear_source(op.child)[1]
    for base in cands:
        r = list(base)
        for j, v in zip(kout, kvals):
            r[cmap[j]] = v
        r = fresh_row(schema, x, table, tuple(r))
        y = f(r)
        if y is not None and op_key(op, y) == key:
            return r
    raise SuffixUnsupported("cannot construct a probe row for this key through the subtree")


def synthesize(schema, view, x, key) -> Tuple[List[Txn], dict]:
    if not view.exposed():
        raise SuffixUnsupported("operator is not exposed (auxiliary exposure view required)")
    op = view.top
    steps: List[Txn] = []
    fam = None
    if isinstance(op, (GroupAgg, Distinct, TopK)):
        rows = rows_at_key(view, x, key)
        table = linear_source(op.child)[0]
        if rows:
            template = rows[0][0]
        else:
            if isinstance(op, TopK):
                raise SuffixUnsupported("empty top-k partition has no state to expose")
            template = key_template(schema, x, table, op, key)
        copies = [(r, y) for r, m, y in rows for _ in range(m)]
        if isinstance(op, TopK):
            fam = "TOPK:drain-from-top"
            copies.sort(key=lambda ry: op.order_key(ry[1]))
        elif isinstance(op, GroupAgg) and op.has_minmax():
            fam = "MINMAX:drain-in-extremum-order+probe"
            fn, col = next((f, c) for f, c in op.aggs if f in ("MIN", "MAX"))
            copies.sort(key=lambda ry: ((ry[1][col] is None), ry[1][col] if ry[1][col] is not None else 0), reverse=False)
            if fn == "MAX":
                nn = [c for c in copies if c[1][col] is not None]; nu = [c for c in copies if c[1][col] is None]
                copies = list(reversed(nn)) + nu
        else:
            fam = ("DISTINCT" if isinstance(op, Distinct) else "GROUP") + ":drain+probe"
        cur = x
        for r, _ in copies:
            t = delete_txn(schema, cur, table, r)
            steps.append(t); cur = apply_txn(cur, t)
        if not isinstance(op, TopK):
            probe = fresh_row(schema, cur, table, template)
            t = Txn({table: ZSet([(probe, 1)])}); steps.append(t); cur = apply_txn(cur, t)
    elif isinstance(op, Join):
        fam = ("LEFTJOIN" if op.outer else "JOIN") + ":probe-both-sides+drain-right"
        cur = x
        for side in ("R", "L"):
            child = child_for(op, side)
            ls = linear_source(child)
            table = ls[0]
            cmap = source_col_map(child)
            kcol = cmap[op.rk if side == "R" else op.lk]
            tmpl = next(iter(sorted(cur[table].d, key=lambda r: str(r))), None)
            if tmpl is None:
                raise SuffixUnsupported("no template row for probe")
            probe = fresh_row(schema, cur, table, tmpl, {kcol: key})
            y = ls[1](probe)
            if y is None or op_key(op, y, side) != key:
                raise SuffixUnsupported("probe row does not pass the subtree filter")
            t_in = Txn({table: ZSet([(probe, 1)])}); steps.append(t_in); cur = apply_txn(cur, t_in)
            t_out = Txn({table: ZSet([(probe, -1)])}); steps.append(t_out); cur = apply_txn(cur, t_out)
        for r, m, _ in rows_at_key(view, cur, key, "R"):
            for _ in range(m):
                t = delete_txn(schema, cur, linear_source(op.right)[0], r); steps.append(t); cur = apply_txn(cur, t)
    else:
        raise SuffixUnsupported(type(op).__name__)
    chk = x
    for i, t in enumerate(steps):
        chk = apply_txn(chk, t)
        ok, why = legal_state(schema, chk)
        if not ok:
            raise SuffixUnsupported(f"suffix step {i} illegal: {why}")
    rec = {"family": fam, "view": view.name, "operator": op.nid, "key": repr(key), "steps": len(steps),
           "reference_state_digest": state_digest(x), "lemma": "D"}
    return steps, rec


# ---------------------------------------------------------------- Amendment v1.4: matched random-suffix control
# Uses the reference schema/state ONLY for legality and same-key targeting. It never calls `synthesize` and never
# orders, drains or probes by distinguishing logic. Sampling distribution (frozen; see RANDOM_SUFFIX_MATCHING_CONTRACT.md):
RANDOM_SUFFIX_POLICY = {
    "p_insert_when_both_possible": 0.5,
    "delete_target": "uniform over current row copies that map to the key (FK cascade as in legal deletes)",
    "insert_base": "uniform over existing rows of the source table plus the same-key template",
    "free_column_values": {"int": [-1, 0, 1, 2, 3], "dec": ["-1", "0", "1", "2"], "text": ["a", "b", "c"]},
    "p_null_for_nullable_free_column": 0.1,
    "insert_retries_before_template_fallback": 8,
    "join_side": "uniform over {L, R}",
}


def opportunity_length(schema, view, x, key) -> int:
    """|c_ref| without constructing c_ref: same support conditions and step count as the characterization suffix,
    computed from the reference per-key state size only (no ordering, no distinguishing policy)."""
    if not view.exposed():
        raise SuffixUnsupported("operator is not exposed (auxiliary exposure view required)")
    op = view.top
    if isinstance(op, (GroupAgg, Distinct, TopK)):
        rows = rows_at_key(view, x, key)
        if not rows:
            if isinstance(op, TopK):
                raise SuffixUnsupported("empty top-k partition has no state to expose")
            key_template(schema, x, linear_source(op.child)[0], op, key)      # same support condition
        n = sum(m for _, m, _ in rows)
        return n + (0 if isinstance(op, TopK) else 1)
    if isinstance(op, Join):
        for side in ("R", "L"):
            child = child_for(op, side); ls = linear_source(child); table = ls[0]
            kcol = source_col_map(child)[op.rk if side == "R" else op.lk]
            tmpl = next(iter(sorted(x[table].d, key=lambda r: str(r))), None)
            if tmpl is None:
                raise SuffixUnsupported("no template row for probe")
            probe = fresh_row(schema, x, table, tmpl, {kcol: key}); y = ls[1](probe)
            if y is None or op_key(op, y, side) != key:
                raise SuffixUnsupported("probe row does not pass the subtree filter")
        return 4 + sum(m for _, m, _ in rows_at_key(view, x, key, "R"))
    raise SuffixUnsupported(type(op).__name__)


def _random_free_value(rng, typ, nullable):
    from decimal import Decimal
    if nullable and rng.random() < RANDOM_SUFFIX_POLICY["p_null_for_nullable_free_column"]:
        return None
    v = rng.choice(RANDOM_SUFFIX_POLICY["free_column_values"][typ])
    return Decimal(v) if typ == "dec" else v


def _random_same_key_insert(schema, cur, op, key, side, rng):
    child = child_for(op, side); ls = linear_source(child); table, f = ls
    tb = schema.tables[table]; cmap = source_col_map(child)
    if isinstance(op, Join):
        kpos = {cmap[op.rk if side == "R" else op.lk]: key}
    else:
        kout = op.gcols if isinstance(op, GroupAgg) else list(range(child.arity))
        kvals = key if isinstance(key, tuple) else (key,)
        kpos = {cmap[j]: v for j, v in zip(kout, kvals)}
    fixed = set(kpos) | set(tb.pk or []) | {i for c, _, _ in tb.fks for i in c}
    bases = sorted(cur[table].d, key=repr)
    for _ in range(RANDOM_SUFFIX_POLICY["insert_retries_before_template_fallback"]):
        base = list(rng.choice(bases)) if bases else None
        if base is None:
            break
        for i, (_, typ, nl) in enumerate(tb.cols):
            if i not in fixed:
                base[i] = _random_free_value(rng, typ, nl)
        r = fresh_row(schema, cur, table, tuple(base), kpos)
        y = f(r)
        if y is not None and op_key(op, y, side) == key:
            return table, r
    if isinstance(op, Join):
        tmpl = next(iter(sorted(cur[table].d, key=lambda r: str(r))), None)
        if tmpl is None:
            raise SuffixUnsupported("no row to base a same-key insert on")
        return table, fresh_row(schema, cur, table, tmpl, kpos)
    return table, key_template(schema, cur, table, op, key)


def random_suffix(schema, view, x, key, length: int, rng) -> List[Txn]:
    """Matched random legal continuation: `length` steps on the same exposed key, every prefix legal."""
    op = view.top; steps: List[Txn] = []; cur = x
    sides = ("L", "R") if isinstance(op, Join) else (None,)
    for _ in range(length):
        side = rng.choice(sides)
        dels = [(r, m) for r, m, _ in rows_at_key(view, cur, key, side)] if side is not None or not isinstance(op, Join) else []
        copies = [r for r, m in dels for _ in range(m)]
        do_insert = (not copies) or rng.random() < RANDOM_SUFFIX_POLICY["p_insert_when_both_possible"]
        t = None
        if not do_insert:
            table = linear_source(child_for(op, side))[0]
            t = delete_txn(schema, cur, table, rng.choice(copies))
        else:
            table, r = _random_same_key_insert(schema, cur, op, key, side, rng)
            t = Txn({table: ZSet([(r, 1)])})
            if not legal_state(schema, apply_txn(cur, t))[0] and copies:
                t = delete_txn(schema, cur, linear_source(child_for(op, side))[0], rng.choice(copies))
        nxt = apply_txn(cur, t)
        ok, why = legal_state(schema, nxt)
        if not ok:
            raise SuffixUnsupported(f"random suffix step illegal: {why}")
        steps.append(t); cur = nxt
    return steps


# ---------------------------------------------------------------- V1.8 pre-execution amendment: deletion-matched control
DELMATCH_POLICY = {"version": 1, "max_order_resamples": 16, "max_insert_attempts": 8}


def is_delete_step(t: Txn) -> bool:
    """A continuation step is a delete step iff every weight it carries is negative (a delete with its FK cascade)."""
    ws = [m for z in t.delta.values() for m in z.d.values()]
    return bool(ws) and all(m < 0 for m in ws)


def deletion_matched_suffix(schema, view, x, key, directed: List[Txn], rng) -> List[Txn]:
    """Matched control (V1.8): same key and length as the directed continuation and exactly as many delete steps,
    placed at uniformly random positions. Deletes pick a uniform same-key row copy (legal FK cascade); inserts follow
    the frozen random-insert rule. Every prefix is legal; infeasible orders are resampled, then fail closed."""
    op = view.top; L = len(directed); nd = sum(1 for t in directed if is_delete_step(t))
    sides = ("L", "R") if isinstance(op, Join) else (None,)
    for _ in range(DELMATCH_POLICY["max_order_resamples"]):
        pos = set(rng.sample(range(L), nd)); steps: List[Txn] = []; cur = x; ok = True
        for i in range(L):
            side = rng.choice(sides); t = None
            if i in pos:
                for sd in [side] + [q for q in sides if q != side]:
                    copies = [r for r, m, _ in rows_at_key(view, cur, key, sd) for _ in range(m)]
                    if copies:
                        t = delete_txn(schema, cur, linear_source(child_for(op, sd))[0], rng.choice(copies)); break
            else:
                for _ in range(DELMATCH_POLICY["max_insert_attempts"]):
                    table, r = _random_same_key_insert(schema, cur, op, key, side, rng)
                    cand = Txn({table: ZSet([(r, 1)])})
                    if legal_state(schema, apply_txn(cur, cand))[0]:
                        t = cand; break
            if t is None or not legal_state(schema, apply_txn(cur, t))[0]:
                ok = False; break
            cur = apply_txn(cur, t); steps.append(t)
        if ok:
            return steps
    raise SuffixUnsupported("deletion-matched continuation infeasible after bounded resampling")
