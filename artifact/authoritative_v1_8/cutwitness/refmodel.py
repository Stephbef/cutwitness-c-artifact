"""Reference model for the frozen SQL subset with per-operator, per-key state and transition labels."""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Dict, List, Optional, Tuple
from .model import ZSet, Row, State, cjson, crow, sha

AVG_Q = Decimal("0.000001")
CMP_OPS = ("=", "<>", "<", "<=", ">", ">=", "IS NULL", "IS NOT NULL")
AGG_FNS = ("COUNT", "SUM", "AVG", "MIN", "MAX")


class UnsupportedSemantics(Exception):
    pass


def sql_sort_key(v):
    # NULLS LAST, numeric order for numbers, code-point order for (ASCII) text
    return (1, 0) if v is None else (0, v)


class Node:
    stateful = False
    kind = "node"

    def __init__(self, nid: str):
        self.nid = nid

    def children(self):
        return []

    def to_json(self):
        raise NotImplementedError("abstract")


class Scan(Node):
    kind = "scan"

    def __init__(self, nid, table: str, arity: int):
        super().__init__(nid); self.table = table; self.arity = arity

    def eval(self, x: State, cache) -> ZSet:
        return x[self.table]

    def to_json(self):
        return {"op": "scan", "table": self.table}


def pred_true(v, op, c) -> bool:
    if op == "IS NULL":
        return v is None
    if op == "IS NOT NULL":
        return v is not None
    if v is None or c is None:
        return False
    return {"=": v == c, "<>": v != c, "<": v < c, "<=": v <= c, ">": v > c, ">=": v >= c}[op]


class Filter(Node):
    kind = "filter"

    def __init__(self, nid, child: Node, preds):
        super().__init__(nid); self.child = child; self.preds = [tuple(p) for p in preds]
        for _, op, _ in self.preds:
            if op not in CMP_OPS:
                raise UnsupportedSemantics(op)
        self.arity = child.arity

    def children(self):
        return [self.child]

    def ok(self, r) -> bool:
        return all(pred_true(r[c], op, k) for c, op, k in self.preds)

    def eval(self, x, cache):
        return ev(self.child, x, cache).filter(self.ok)

    def to_json(self):
        return {"op": "filter", "preds": [[c, o, crow((k,))[0]] for c, o, k in self.preds], "child": self.child.to_json()}


class Project(Node):
    kind = "project"

    def __init__(self, nid, child: Node, cols):
        super().__init__(nid); self.child = child; self.cols = list(cols); self.arity = len(self.cols)

    def children(self):
        return [self.child]

    def map(self, r):
        return tuple(r[i] for i in self.cols)

    def eval(self, x, cache):
        z = ZSet()
        for r, m in ev(self.child, x, cache).d.items():
            z.add_row(self.map(r), m)
        return z

    def to_json(self):
        return {"op": "project", "cols": self.cols, "child": self.child.to_json()}


class Join(Node):
    stateful = True
    kind = "join"
    outer = False

    def __init__(self, nid, left: Node, right: Node, lk: int, rk: int):
        super().__init__(nid); self.left = left; self.right = right; self.lk = lk; self.rk = rk
        self.arity = left.arity + right.arity

    def children(self):
        return [self.left, self.right]

    def key_rows(self, x, cache):
        out = {}
        for side, ch, kc in (("L", self.left, self.lk), ("R", self.right, self.rk)):
            for r, m in ev(ch, x, cache).d.items():
                k = r[kc]
                st = out.setdefault(k, (ZSet(), ZSet()))
                (st[0] if side == "L" else st[1]).add_row(r, m)
        return out

    def key_output(self, k, st) -> ZSet:
        L, R = st
        z = ZSet()
        rnull = (None,) * self.right.arity
        rpos = [(r, m) for r, m in R.d.items() if m > 0] if k is not None else []
        for l, ml in L.d.items():
            if rpos:
                for r, mr in rpos:
                    z.add_row(l + r, ml * mr)
            elif self.outer:
                z.add_row(l + rnull, ml)
        return z

    def eval(self, x, cache):
        z = ZSet()
        for k, st in self.key_rows(x, cache).items():
            z = z + self.key_output(k, st)
        return z

    def to_json(self):
        return {"op": "leftjoin" if self.outer else "join", "lk": self.lk, "rk": self.rk,
                "left": self.left.to_json(), "right": self.right.to_json()}


class LeftJoin(Join):
    kind = "leftjoin"
    outer = True


def agg_value(fn, col, bag: ZSet):
    if fn == "COUNT":
        if col is None:
            return sum(m for m in bag.d.values())
        return sum(m for r, m in bag.d.items() if r[col] is not None)
    vals = [(r[col], m) for r, m in bag.d.items() if r[col] is not None and m > 0]
    if fn == "SUM":
        if not vals:
            return None
        s = 0
        for v, m in vals:
            s = s + v * m
        return s
    if fn == "AVG":
        if not vals:
            return None
        s = sum(Decimal(v) * m for v, m in vals); c = sum(m for _, m in vals)
        return (s / Decimal(c)).quantize(AVG_Q, rounding=ROUND_HALF_EVEN)
    if fn == "MIN":
        return min(v for v, _ in vals) if vals else None
    if fn == "MAX":
        return max(v for v, _ in vals) if vals else None
    raise UnsupportedSemantics(fn)


class GroupAgg(Node):
    stateful = True
    kind = "group"

    def __init__(self, nid, child: Node, gcols, aggs):
        super().__init__(nid); self.child = child; self.gcols = list(gcols); self.aggs = [tuple(a) for a in aggs]
        if not self.gcols:
            raise UnsupportedSemantics("global aggregate without GROUP BY is out of scope")
        for fn, _ in self.aggs:
            if fn not in AGG_FNS:
                raise UnsupportedSemantics(fn)
        self.arity = len(self.gcols) + len(self.aggs)

    def children(self):
        return [self.child]

    def has_minmax(self):
        return any(fn in ("MIN", "MAX") for fn, _ in self.aggs)

    def key_rows(self, x, cache):
        out = {}
        for r, m in ev(self.child, x, cache).d.items():
            k = tuple(r[i] for i in self.gcols)
            out.setdefault(k, ZSet()).add_row(r, m)
        return out

    def key_output(self, k, bag: ZSet) -> ZSet:
        z = ZSet()
        if bag.total() > 0:
            z.add_row(tuple(k) + tuple(agg_value(fn, c, bag) for fn, c in self.aggs), 1)
        return z

    def eval(self, x, cache):
        z = ZSet()
        for k, bag in self.key_rows(x, cache).items():
            z = z + self.key_output(k, bag)
        return z

    def to_json(self):
        return {"op": "group", "gcols": self.gcols, "aggs": [list(a) for a in self.aggs], "child": self.child.to_json()}


class Distinct(Node):
    stateful = True
    kind = "distinct"

    def __init__(self, nid, child: Node):
        super().__init__(nid); self.child = child; self.arity = child.arity

    def children(self):
        return [self.child]

    def key_rows(self, x, cache):
        out = {}
        for r, m in ev(self.child, x, cache).d.items():
            out.setdefault(r, ZSet()).add_row(r, m)
        return out

    def key_output(self, k, bag):
        z = ZSet()
        if bag.total() > 0:
            z.add_row(k, 1)
        return z

    def eval(self, x, cache):
        z = ZSet()
        for k, bag in self.key_rows(x, cache).items():
            z = z + self.key_output(k, bag)
        return z

    def to_json(self):
        return {"op": "distinct", "child": self.child.to_json()}


class TopK(Node):
    stateful = True
    kind = "topk"

    def __init__(self, nid, child: Node, pcols, ocols, k: int):
        super().__init__(nid); self.child = child; self.pcols = list(pcols); self.ocols = list(ocols); self.k = int(k)
        if self.k < 1 or not self.pcols or not self.ocols:
            raise UnsupportedSemantics("top-k needs k>=1, partition and order columns")
        self.arity = child.arity

    def children(self):
        return [self.child]

    def order_key(self, r):
        return tuple(sql_sort_key(r[i]) for i in self.ocols) + tuple(sql_sort_key(v) for v in r)

    def ranked(self, bag: ZSet):
        copies = []
        for r, m in bag.d.items():
            copies.extend([r] * max(m, 0))
        copies.sort(key=self.order_key)
        return copies

    def key_rows(self, x, cache):
        out = {}
        for r, m in ev(self.child, x, cache).d.items():
            out.setdefault(tuple(r[i] for i in self.pcols), ZSet()).add_row(r, m)
        return out

    def key_output(self, k, bag):
        z = ZSet()
        for r in self.ranked(bag)[: self.k]:
            z.add_row(r, 1)
        return z

    def eval(self, x, cache):
        z = ZSet()
        for k, bag in self.key_rows(x, cache).items():
            z = z + self.key_output(k, bag)
        return z

    def to_json(self):
        return {"op": "topk", "pcols": self.pcols, "ocols": self.ocols, "k": self.k, "child": self.child.to_json()}


def ev(node: Node, x: State, cache: Optional[dict] = None) -> ZSet:
    if cache is None:
        cache = {}
    key = id(node)
    if key not in cache:
        cache[key] = node.eval(x, cache)
    return cache[key]


def stateful_ops(node: Node) -> List[Node]:
    out = []
    for c in node.children():
        out.extend(stateful_ops(c))
    if node.stateful:
        out.append(node)
    return out


def linear_source(node: Node):
    """If node is a Scan/Filter/Project chain, return (table, fn source_row -> output_row or None)."""
    if isinstance(node, Scan):
        return node.table, (lambda r: r)
    if isinstance(node, Filter):
        s = linear_source(node.child)
        if s is None:
            return None
        t, f = s
        return t, (lambda r, f=f: (lambda y: y if (y is not None and node.ok(y)) else None)(f(r)))
    if isinstance(node, Project):
        s = linear_source(node.child)
        if s is None:
            return None
        t, f = s
        return t, (lambda r, f=f: (lambda y: None if y is None else node.map(y))(f(r)))
    return None


class View:
    def __init__(self, name: str, root: Node):
        self.name = name; self.root = root
        self.ops = stateful_ops(root)
        if not self.ops:
            raise UnsupportedSemantics("view without stateful operator is out of scope")

    @property
    def top(self) -> Node:
        return self.ops[-1]

    def exposed(self) -> bool:
        n = self.root
        while not n.stateful:
            if not isinstance(n, (Filter, Project)):
                return False
            n = n.child
        return n is self.top and all(linear_source(c) is not None for c in self.top.children())

    def eval(self, x: State) -> ZSet:
        return ev(self.root, x, {})

    def to_json(self):
        return {"name": self.name, "plan": self.root.to_json()}

    def digest(self):
        return sha(self.to_json())


# ---------------------------------------------------------------- per-key state and transition labels

def per_key(op: Node, x: State, cache=None) -> Dict[Any, Any]:
    return op.key_rows(x, cache if cache is not None else {})


def _size_class(n: int) -> str:
    return "0" if n <= 0 else ("1" if n == 1 else "M")


def _minmax_profile(op: GroupAgg, bag: ZSet):
    fn, col = next((f, c) for f, c in op.aggs if f in ("MIN", "MAX"))
    vals = [(r[col], m) for r, m in bag.d.items() if r[col] is not None and m > 0]
    if not vals:
        return None, 0
    ext = min(v for v, _ in vals) if fn == "MIN" else max(v for v, _ in vals)
    return ext, sum(m for v, m in vals if v == ext)


def _better(op: GroupAgg, a, b) -> bool:
    fn = next(f for f, c in op.aggs if f in ("MIN", "MAX"))
    return a < b if fn == "MIN" else a > b


def labels_for(op: Node, before, after, delta) -> List[Tuple[str, str, Tuple[str, ...]]]:
    """Return [(automaton, base_label, refinement_tags)] for one (operator, key) transition."""
    out = []
    if isinstance(op, GroupAgg):
        n0, n1 = before.total(), after.total()
        if n0 <= 0 and n1 == 1: lab = "birth"
        elif n0 <= 0 and n1 > 1: lab = "bulk-birth"
        elif n0 > 0 and n1 <= 0: lab = "death" if n0 == 1 else "bulk-death"
        elif n1 > n0: lab = "grow"
        elif n1 < n0: lab = "shrink"
        else: lab = "replace"
        tags = []
        if any(r[c] is None for r in delta.d for fn, c in op.aggs if c is not None): tags.append("null")
        for fn, c in op.aggs:
            if fn == "SUM" and n0 > 0 and n1 > 0:
                s0, s1 = agg_value("SUM", c, before), agg_value("SUM", c, after)
                if s0 is not None and s1 is not None and (s1 == 0 or (s0 > 0) != (s1 > 0)) and s0 != s1:
                    tags.append("sum-zero"); break
        if any(m > 1 for m in after.d.values()): tags.append("dup")
        if delta.has_pos_and_neg(): tags.append("mixed")
        out.append(("GROUP", lab, tuple(tags)))
        if op.has_minmax():
            e0, c0 = _minmax_profile(op, before); e1, c1 = _minmax_profile(op, after)
            if e0 is None and e1 is not None: ml = "birth"
            elif e0 is not None and e1 is None: ml = "death"
            elif e0 is None and e1 is None: ml = "non-ext"
            elif e1 != e0: ml = "ext-improve" if _better(op, e1, e0) else "ext-remove-unique"
            elif c1 > c0: ml = "ext-tie"
            elif c1 < c0: ml = "ext-remove-tied"
            else: ml = "non-ext"
            out.append(("MINMAX", ml, tuple(t for t in tags if t in ("null", "mixed"))))
        return out
    if isinstance(op, Distinct):
        m0, m1 = before.total(), after.total()
        if m0 <= 0 and m1 > 0: lab = "appear"
        elif m0 > 0 and m1 <= 0: lab = "disappear"
        elif m1 > m0: lab = "add-dup"
        elif m1 < m0: lab = "remove-dup"
        else: lab = "replace"
        return [("DISTINCT", lab, ("mixed",) if delta.has_pos_and_neg() else ())]
    if isinstance(op, Join):
        (L0, R0), (L1, R1) = before, after
        dL, dR = delta
        l0, r0, l1, r1 = L0.total(), R0.total(), L1.total(), R1.total()
        parts = []
        for side, d, other0 in (("L", dL, r0), ("R", dR, l0)):
            if d:
                op_ = "mix" if d.has_pos_and_neg() else ("ins" if d.total() > 0 else "del")
                parts.append(f"{side}-{op_}-{'p' if other0 > 0 else 'np'}")
        lab = "+".join(parts) if parts else "none"
        tags = []
        if (l1 <= 0 < l0 and r1 > 0) or (r1 <= 0 < r0 and l1 > 0):
            tags.append("last-partner-loss")
        out = [("JOIN", lab, tuple(tags))]
        if op.outer:
            pad0, pad1 = (l0 > 0 and r0 <= 0), (l1 > 0 and r1 <= 0)
            pl = "pad-enter" if (pad1 and not pad0) else ("pad-leave" if (pad0 and not pad1) else "pad-none")
            out.append(("LEFTJOIN", pl, ()))
        return out
    if isinstance(op, TopK):
        rb, ra = op.ranked(before), op.ranked(after)
        topb, topa = rb[: op.k], ra[: op.k]
        n0 = len(rb)
        net = delta.total()
        changed_top = topb != topa
        if net > 0:
            lab = ("enter" if n0 < op.k else "enter-evict") if changed_top else "insert-below"
        elif net < 0:
            lab = ("delete-refill" if n0 > op.k else "delete-shrink") if changed_top else "delete-below"
        else:
            lab = "replace-top" if changed_top else "replace-below"
        tags = []
        if len(ra) > op.k and op.order_key(ra[op.k - 1])[: len(op.ocols)] == op.order_key(ra[op.k])[: len(op.ocols)]:
            tags.append("boundary-tie")
        return [("TOPK", lab, tuple(tags))]
    raise UnsupportedSemantics(type(op).__name__)


def empty_key_state(op: Node):
    return (ZSet(), ZSet()) if isinstance(op, Join) else ZSet()


def key_delta(op: Node, before, after):
    if isinstance(op, Join):
        return (after[0] - before[0], after[1] - before[1])
    return after - before


def touched(view: View, x0: State, x1: State) -> Dict[Tuple[str, Any], Tuple[Any, Any, Any]]:
    """Context-sensitive K_o(delta | x0): {(op_id, key): (before, after, per-key delta)} for every stateful op."""
    c0, c1 = {}, {}
    out = {}
    for op in view.ops:
        b, a = per_key(op, x0, c0), per_key(op, x1, c1)
        for k in set(b) | set(a):
            sb, sa = b.get(k, empty_key_state(op)), a.get(k, empty_key_state(op))
            same = (sb == sa) if not isinstance(op, Join) else (sb[0] == sa[0] and sb[1] == sa[1])
            if not same:
                out[(op.nid, k)] = (sb, sa, key_delta(op, sb, sa))
    return out


# ---------------------------------------------------------------- SQL generation for O3 / engines

def sql_lit(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, Decimal):
        return f"CAST('{format(v, 'f')}' AS DECIMAL(18,4))"
    return "'" + v.replace("'", "''") + "'"


def to_sql(node: Node) -> str:
    """SQL producing columns c0..c{n-1}; AVG is emitted as two columns (sum, count) -- see view_sql_postprocess."""
    if isinstance(node, Scan):
        return f"SELECT * FROM {node.table}"
    if isinstance(node, Filter):
        conds = []
        for c, op, k in node.preds:
            conds.append(f"c{c} {op}" if op in ("IS NULL", "IS NOT NULL") else f"c{c} {op} {sql_lit(k)}")
        return f"SELECT * FROM ({to_sql(node.child)}) WHERE " + " AND ".join(conds)
    if isinstance(node, Project):
        return "SELECT " + ", ".join(f"c{i} AS c{j}" for j, i in enumerate(node.cols)) + f" FROM ({to_sql(node.child)})"
    if isinstance(node, Join):
        la, ra = node.left.arity, node.right.arity
        cols = [f"l.c{i} AS c{i}" for i in range(la)] + [f"r.c{i} AS c{la + i}" for i in range(ra)]
        jt = "LEFT JOIN" if node.outer else "JOIN"
        return (f"SELECT {', '.join(cols)} FROM ({to_sql(node.left)}) l {jt} ({to_sql(node.right)}) r "
                f"ON l.c{node.lk} = r.c{node.rk}")
    if isinstance(node, GroupAgg):
        sel = [f"c{g} AS g{j}" for j, g in enumerate(node.gcols)]
        for j, (fn, c) in enumerate(node.aggs):
            if fn == "COUNT":
                sel.append(f"COUNT({'*' if c is None else f'c{c}'}) AS a{j}")
            elif fn == "AVG":
                sel.append(f"SUM(c{c}) AS a{j}s"); sel.append(f"COUNT(c{c}) AS a{j}n")
            else:
                sel.append(f"{fn}(c{c}) AS a{j}")
        grp = ", ".join(f"c{g}" for g in node.gcols)
        return f"SELECT {', '.join(sel)} FROM ({to_sql(node.child)}) GROUP BY {grp}"
    if isinstance(node, Distinct):
        return f"SELECT DISTINCT * FROM ({to_sql(node.child)})"
    if isinstance(node, TopK):
        n = node.arity
        part = ", ".join(f"c{i}" for i in node.pcols)
        order = ", ".join([f"c{i} ASC NULLS LAST" for i in node.ocols] + [f"c{i} ASC NULLS LAST" for i in range(n)])
        cols = ", ".join(f"c{i}" for i in range(n))
        return (f"SELECT {cols} FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY {part} ORDER BY {order}) AS rn__ "
                f"FROM ({to_sql(node.child)})) WHERE rn__ <= {node.k}")
    raise UnsupportedSemantics(type(node).__name__)


def view_sql(view: View) -> str:
    return to_sql(view.root)


def view_sql_postprocess(view: View, rows) -> ZSet:
    """Convert raw SQL rows into canonical view rows (exact AVG from SUM/COUNT; ints normalized)."""
    z = ZSet()
    root = view.root
    if isinstance(root, GroupAgg):
        for r in rows:
            r = list(r); out = list(r[: len(root.gcols)]); i = len(root.gcols)
            for fn, c in root.aggs:
                if fn == "AVG":
                    s, n = r[i], r[i + 1]; i += 2
                    out.append(None if (s is None or not n) else (Decimal(s) / Decimal(n)).quantize(AVG_Q, rounding=ROUND_HALF_EVEN))
                else:
                    out.append(r[i]); i += 1
            z.add_row(tuple(normalize_value(v) for v in out), 1)
        return z
    for r in rows:
        z.add_row(tuple(normalize_value(v) for v in r), 1)
    return z


def normalize_value(v):
    if isinstance(v, bool):
        raise TypeError("bool result is outside the frozen subset")
    if isinstance(v, float):
        raise TypeError("floating result is outside the exact frozen subset")
    return v


def plan_from_json(j: dict, nid_prefix: str, arities: Dict[str, int], counter=None) -> Node:
    counter = counter if counter is not None else [0]
    counter[0] += 1
    nid = f"{nid_prefix}/n{counter[0]}"
    op = j["op"]
    if op == "scan":
        return Scan(nid, j["table"], arities[j["table"]])
    if op == "filter":
        from .model import uncval
        return Filter(nid, plan_from_json(j["child"], nid_prefix, arities, counter), [(c, o, uncval(k)) for c, o, k in j["preds"]])
    if op == "project":
        return Project(nid, plan_from_json(j["child"], nid_prefix, arities, counter), j["cols"])
    if op in ("join", "leftjoin"):
        cls = LeftJoin if op == "leftjoin" else Join
        return cls(nid, plan_from_json(j["left"], nid_prefix, arities, counter), plan_from_json(j["right"], nid_prefix, arities, counter), j["lk"], j["rk"])
    if op == "group":
        return GroupAgg(nid, plan_from_json(j["child"], nid_prefix, arities, counter), j["gcols"], [tuple(a) for a in j["aggs"]])
    if op == "distinct":
        return Distinct(nid, plan_from_json(j["child"], nid_prefix, arities, counter))
    if op == "topk":
        return TopK(nid, plan_from_json(j["child"], nid_prefix, arities, counter), j["pcols"], j["ocols"], j["k"])
    raise UnsupportedSemantics(op)
