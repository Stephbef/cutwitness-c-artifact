"""W3: deterministic generated operator-focused workload (frozen grammar)."""
from __future__ import annotations
import random
from decimal import Decimal
from typing import List
from .model import Schema, Table, Txn, ZSet, apply_txn, empty_state, legal_state
from .refmodel import Distinct, Filter, GroupAgg, Join, LeftJoin, Project, Scan, TopK, View

KDOM = [1, 2, 3, 4]
VDOM = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4.5"), Decimal("-2"), None]
SDOM = ["a", "b", "c"]


def gen_schema(rng: random.Random) -> Schema:
    n = rng.randint(2, 4)
    tables = [Table("t0", [("id", "int", False), ("k", "int", False), ("v", "dec", True), ("s", "text", False)], pk=[0])]
    for i in range(1, n):
        fk = rng.random() < 0.5
        cols = [("id", "int", False), ("k", "int", False), ("v", "dec", True), ("s", "text", False)]
        fks = []
        if fk:
            cols.append(("p", "int", True)); fks = [([4], "t0", [0])]
        tables.append(Table(f"t{i}", cols, pk=[0], fks=fks))
    return Schema(tables)


def gen_views(rng: random.Random, schema: Schema) -> List[View]:
    ar = {n: schema.tables[n].arity for n in schema.order}
    a, b = "t0", rng.choice(schema.order[1:])
    vs = []
    f = Filter("vg/f", Scan("vg/s", a, ar[a]), [(2, "IS NOT NULL", None)] if rng.random() < 0.3 else [(1, ">=", 1)])
    vs.append(View("v_group", GroupAgg("vg/g", f, [1], [("COUNT", None), ("SUM", 2), ("AVG", 2), ("MIN", 2)])))
    vs.append(View("v_distinct", Distinct("vd/d", Project("vd/p", Scan("vd/s", b, ar[b]), [1, 3]))))
    vs.append(View("v_topk", TopK("vt/t", Scan("vt/s", a, ar[a]), [1], [2], 2)))
    L = lambda p: Project(f"{p}/pl", Scan(f"{p}/sl", a, ar[a]), [0, 1, 2])
    R = lambda p: Project(f"{p}/pr", Scan(f"{p}/sr", b, ar[b]), [0, 1, 3])
    vs.append(View("v_join", Join("vj/j", L("vj"), R("vj"), 1, 1)))
    vs.append(View("v_ljoin", LeftJoin("vl/j", L("vl"), R("vl"), 1, 1)))
    vs.append(View("v_stacked", GroupAgg("vs/g", Join("vs/j", L("vs"), R("vs"), 1, 1), [1], [("COUNT", None), ("SUM", 2)])))
    return vs


def _new_row(rng, schema, x, t):
    tb = schema.tables[t]
    used = [r[0] for r in x[t].d]
    rid = (max(used) + 1) if used else 1
    row = [rid, rng.choice(KDOM), rng.choice(VDOM), rng.choice(SDOM)]
    if tb.arity == 5:
        parents = sorted(r[0] for r in x["t0"].d)
        row.append(rng.choice(parents + [None]) if parents else None)
    return tuple(row)


def gen_history(rng: random.Random, schema: Schema, n_txn: int, max_rows: int = 3) -> List[Txn]:
    x = empty_state(schema)
    h = []
    for _ in range(n_txn):
        for _attempt in range(20):
            d = {}
            cur = x
            for _r in range(rng.randint(1, max_rows)):
                t = rng.choice(schema.order)
                existing = sorted(cur[t].d)
                op = rng.random()
                if existing and op < 0.3:
                    r = rng.choice(existing)
                    z = ZSet([(r, -1)])
                elif existing and op < 0.5:
                    r = rng.choice(existing)
                    nr = list(r); nr[1] = rng.choice(KDOM); nr[2] = rng.choice(VDOM)
                    z = ZSet([(r, -1), (tuple(nr), 1)])
                else:
                    z = ZSet([(_new_row(rng, schema, cur, t), 1)])
                d[t] = d.get(t, ZSet()) + z
                cur = apply_txn(cur, Txn({t: z}))
            txn = Txn(d)
            if txn.is_empty():
                continue
            x1 = apply_txn(x, txn)
            if legal_state(schema, x1)[0]:
                h.append(txn); x = x1; break
    return h
