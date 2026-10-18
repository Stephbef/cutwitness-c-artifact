"""Plan inversion: realize a semantic k-word at a fresh key of an exposed operator, with exact post-check."""
from __future__ import annotations
from decimal import Decimal
from typing import List, Optional, Tuple
from .model import Txn, ZSet, apply_txn, legal_state
from .refmodel import Distinct, GroupAgg, Join, TopK, labels_for, linear_source, touched
from .suffix import child_for, op_key, rows_at_key, source_col_map, SuffixUnsupported

PALETTE = {"int": [1, 2, 3], "dec": [Decimal("1"), Decimal("2"), Decimal("3")], "text": ["a", "b", "c"]}


class Unrealizable(Exception):
    pass


def _fresh_key_values(x, table, col, typ, n=4):
    used = {r[col] for r in x[table].d}
    if typ == "int":
        base = max([v for v in used if isinstance(v, int)] + [0]) + 1000
        return [base + i for i in range(n)] + [-(base + i) for i in range(n)]
    if typ == "text":
        return [f"k{len(used) + i}" for i in range(n)]
    return [Decimal(1000 + i) for i in range(n)]


def _row_for(schema, x, table, child, keycols_vals, value_choice: int, nullable_null: bool):
    tb = schema.tables[table]
    r = []
    for i, (_, typ, nl) in enumerate(tb.cols):
        if i in keycols_vals:
            r.append(keycols_vals[i]); continue
        fk = next(((c, p, pc) for c, p, pc in tb.fks if i in c), None)
        if fk is not None:
            c, p, pc = fk
            parents = sorted(x[p].d, key=lambda rr: str(rr))
            if not parents:
                raise Unrealizable(f"no parent rows for foreign key {table}->{p}")
            r.append(parents[0][pc[c.index(i)]]); continue
        if tb.pk is not None and i in tb.pk:
            used = [rr[i] for rr in x[table].d if isinstance(rr[i], int)]
            r.append((max(used) + 1) if used else 1); continue
        if nullable_null and nl:
            r.append(None); continue
        pal = PALETTE[typ]
        r.append(pal[value_choice % len(pal)])
    row = tuple(r)
    ls = linear_source(child)
    if ls[1](row) is None:
        return None
    return row


def realize(schema, view, base, automaton: str, word: Tuple[str, ...], setup_max: int = 2, budget: int = 400):
    op = view.top
    if not view.exposed():
        raise Unrealizable("operator not exposed")
    sides = ["L", "R"] if isinstance(op, Join) else [None]
    # choose a fresh key
    side0 = sides[0]
    child0 = child_for(op, side0)
    table0 = linear_source(child0)[0]
    cmap0 = source_col_map(child0)
    if isinstance(op, GroupAgg):
        kout = op.gcols
    elif isinstance(op, TopK):
        kout = op.pcols
    elif isinstance(op, Join):
        kout = [op.lk]
    else:
        kout = list(range(child0.arity))
    keysrc = [cmap0[j] for j in kout]
    tb0 = schema.tables[table0]
    key = None; keyvals = None
    for cand in range(4):
        vals = {}
        for c in keysrc:
            vals[c] = _fresh_key_values(base, table0, c, tb0.cols[c][1])[cand]
        row = _row_for(schema, base, table0, child0, vals, 0, False)
        if row is not None:
            key = op_key(op, linear_source(child0)[1](row), side0); keyvals = vals; break
    if key is None:
        raise Unrealizable("subtree filter rejects every fresh key candidate")

    def actions(x):
        acts = []
        for side in sides:
            child = child_for(op, side)
            table = linear_source(child)[0]
            cmap = source_col_map(child)
            kc = [cmap[j] for j in (kout if side != "R" else [op.rk])]
            vals = {c: (keyvals[keysrc[0]] if side == "R" else keyvals[c]) for c in kc} if side == "R" else dict(keyvals)
            for vc in range(3):
                for nn in (False, True):
                    row = _row_for(schema, x, table, child, vals, vc, nn)
                    if row is not None:
                        acts.append(Txn({table: ZSet([(row, 1)])}))
                    if row is not None and schema.tables[table].pk is None:
                        acts.append(Txn({table: ZSet([(row, 2)])}))
            for r, m, _ in rows_at_key(view, x, key, side):
                acts.append(Txn({table: ZSet([(r, -1)])}))
                if m > 1:
                    acts.append(Txn({table: ZSet([(r, -m)])}))
        uniq, seen = [], set()
        for a in acts:
            c = str(a.canon())
            if c not in seen:
                seen.add(c); uniq.append(a)
        return uniq

    def label_of(x0, t):
        x1 = apply_txn(x0, t)
        ok, _ = legal_state(schema, x1)
        if not ok:
            return None, x1
        tch = touched(view, x0, x1)
        ent = tch.get((op.nid, key))
        if ent is None:
            return "none", x1
        for aut, lab, _ in labels_for(op, *ent):
            if aut == automaton:
                return lab, x1
        return "none", x1

    nodes = [0]

    def dfs(x, frag, need, setup_left):
        nodes[0] += 1
        if nodes[0] > budget:
            return None
        if not need:
            return frag
        for t in actions(x):
            lab, x1 = label_of(x, t)
            if lab is None:
                continue
            if lab == need[0]:
                r = dfs(x1, frag + [t], need[1:], 0)
                if r is not None:
                    return r
        if setup_left > 0:
            for t in actions(x):
                lab, x1 = label_of(x, t)
                if lab is None:
                    continue
                r = dfs(x1, frag + [t], need, setup_left - 1)
                if r is not None:
                    return r
        return None

    frag = dfs(base, [], list(word), setup_max)
    if frag is None:
        raise Unrealizable(f"no realization within setup<={setup_max}, budget={budget}")
    # exact post-check
    x = base; labs = []
    for t in frag:
        lab, x = label_of(x, t)
        if lab not in (None, "none"):
            labs.append(lab)
    if tuple(labs[-len(word):]) != tuple(word):
        raise Unrealizable("post-check failed")
    return frag, {"automaton": automaton, "word": list(word), "key": repr(key), "key_value": key, "fragment_len": len(frag),
                  "status": "REALIZED", "post_check": "exact"}
