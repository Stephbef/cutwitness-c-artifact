"""W2: deterministic TPC-H-shaped generator with RF1/RF2 refresh streams (spec structure; not dbgen byte-identical)."""
from __future__ import annotations
import random
from decimal import Decimal
from typing import List
from .model import Schema, Table, Txn, ZSet, apply_txn, empty_state, legal_state
from .refmodel import Distinct, Filter, GroupAgg, Join, LeftJoin, Project, Scan, TopK, View

W2_METADATA = {"shape": "TPC-H-shaped; NOT byte-identical to dbgen output",
               "revenue_measure": "SUM(l_extendedprice): the frozen operator subset has no arithmetic, so l_extendedprice*(1-l_discount) is not used",
               "refresh": "RF1 inserts new orders with lineitems; RF2 deletes the oldest orders with their lineitems"}

REGIONS = ["AFRICA", "AMERICA", "ASIA", "EUROPE", "MIDDLE EAST"]
NATIONS = [("ALGERIA", 0), ("ARGENTINA", 1), ("BRAZIL", 1), ("CANADA", 1), ("EGYPT", 4), ("ETHIOPIA", 0), ("FRANCE", 3),
           ("GERMANY", 3), ("INDIA", 2), ("INDONESIA", 2), ("IRAN", 4), ("IRAQ", 4), ("JAPAN", 2), ("JORDAN", 4), ("KENYA", 0),
           ("MOROCCO", 0), ("MOZAMBIQUE", 0), ("PERU", 1), ("CHINA", 2), ("ROMANIA", 3), ("SAUDI ARABIA", 4), ("VIETNAM", 2),
           ("RUSSIA", 3), ("UNITED KINGDOM", 3), ("UNITED STATES", 1)]
TYPES = ["STANDARD ANODIZED TIN", "SMALL PLATED COPPER", "PROMO BURNISHED NICKEL", "ECONOMY BRUSHED STEEL", "LARGE POLISHED BRASS"]


def schema() -> Schema:
    return Schema([
        Table("region", [("r_regionkey", "int", False), ("r_name", "text", False)], pk=[0]),
        Table("nation", [("n_nationkey", "int", False), ("n_name", "text", False), ("n_regionkey", "int", False)], pk=[0], fks=[([2], "region", [0])]),
        Table("supplier", [("s_suppkey", "int", False), ("s_nationkey", "int", False), ("s_acctbal", "dec", False)], pk=[0], fks=[([1], "nation", [0])]),
        Table("part", [("p_partkey", "int", False), ("p_type", "text", False), ("p_retailprice", "dec", False)], pk=[0]),
        Table("customer", [("c_custkey", "int", False), ("c_nationkey", "int", False), ("c_acctbal", "dec", False)], pk=[0], fks=[([1], "nation", [0])]),
        Table("orders", [("o_orderkey", "int", False), ("o_custkey", "int", False), ("o_totalprice", "dec", False)], pk=[0], fks=[([1], "customer", [0])]),
        Table("lineitem", [("l_orderkey", "int", False), ("l_linenumber", "int", False), ("l_partkey", "int", False), ("l_suppkey", "int", False),
                           ("l_extendedprice", "dec", False), ("l_nationkey", "int", False)], pk=[0, 1],
              fks=[([0], "orders", [0]), ([2], "part", [0]), ([3], "supplier", [0])]),
    ])


def _money(rng, lo, hi) -> Decimal:
    return Decimal(rng.randint(lo * 100, hi * 100)) / 100


def initial(rng: random.Random, sf_units: int = 1):
    """Initial load as one transaction; sf_units scales customers/orders (1 unit = 30 customers, 150 orders)."""
    d = {t: ZSet() for t in ("region", "nation", "supplier", "part", "customer", "orders", "lineitem")}
    for i, r in enumerate(REGIONS):
        d["region"].add_row((i, r), 1)
    for i, (n, r) in enumerate(NATIONS):
        d["nation"].add_row((i, n, r), 1)
    for s in range(1, 10 * sf_units + 1):
        d["supplier"].add_row((s, rng.randrange(25), _money(rng, -999, 9999)), 1)
    for p in range(1, 20 * sf_units + 1):
        d["part"].add_row((p, rng.choice(TYPES), _money(rng, 900, 2000)), 1)
    ncust = 30 * sf_units
    for c in range(1, ncust + 1):
        d["customer"].add_row((c, rng.randrange(25), _money(rng, -999, 9999)), 1)
    nxt = 1
    for _ in range(150 * sf_units):
        d, nxt = _order(rng, d, nxt, ncust, sf_units)
    return Txn(d), nxt


def _order(rng, d, ok, ncust, sf_units):
    cust = rng.randint(1, ncust)
    n_lines = rng.randint(1, 4)
    total = Decimal(0)
    for ln in range(1, n_lines + 1):
        price = _money(rng, 900, 100000)
        total += price
        d["lineitem"].add_row((ok, ln, rng.randint(1, 20 * sf_units), rng.randint(1, 10 * sf_units), price, rng.randrange(25)), 1)
    d["orders"].add_row((ok, cust, total), 1)
    return d, ok + 1


def refresh_stream(rng: random.Random, sch: Schema, n_pairs: int, sf_units: int = 1) -> List[Txn]:
    """Alternating RF1 (insert new orders with lineitems) and RF2 (delete oldest orders with lineitems), ~0.1% x scale."""
    init, nxt = initial(rng, sf_units)
    x = apply_txn(empty_state(sch), init)
    h = [init]
    ncust = 30 * sf_units
    per = max(1, 150 * sf_units // 100)
    for _ in range(n_pairs):
        d = {"orders": ZSet(), "lineitem": ZSet()}
        for _k in range(per):
            d, nxt = _order(rng, d, nxt, ncust, sf_units)
        rf1 = Txn(d); h.append(rf1); x = apply_txn(x, rf1)
        oldest = sorted(r[0] for r in x["orders"].d)[:per]
        d2 = {"orders": ZSet(), "lineitem": ZSet()}
        for r in list(x["orders"].d):
            if r[0] in oldest:
                d2["orders"].add_row(r, -1)
        for r in list(x["lineitem"].d):
            if r[0] in oldest:
                d2["lineitem"].add_row(r, -1)
        rf2 = Txn(d2); h.append(rf2); x = apply_txn(x, rf2)
        assert legal_state(sch, x)[0]
    return h


def views(sch: Schema) -> List[View]:
    ar = {n: sch.tables[n].arity for n in sch.order}
    S = lambda p, t: Scan(f"{p}/s_{t}", t, ar[t])
    return [
        View("w2_revenue_per_nation", GroupAgg("w2r/g", Project("w2r/p", S("w2r", "lineitem"), [5, 4]), [0], [("COUNT", None), ("SUM", 1), ("AVG", 1)])),
        View("w2_price_range_per_type", GroupAgg("w2t/g", Project("w2t/p", S("w2t", "part"), [1, 2]), [0], [("MIN", 1), ("MAX", 1)])),
        View("w2_supplier_nations", Distinct("w2d/d", Project("w2d/p", S("w2d", "lineitem"), [3, 5]))),
        View("w2_customer_orders", LeftJoin("w2l/j", Project("w2l/pc", S("w2l", "customer"), [0, 1]), Project("w2l/po", S("w2l", "orders"), [0, 1]), 0, 1)),
        View("w2_top_orders_per_customer", TopK("w2k/t", Project("w2k/p", S("w2k", "orders"), [1, 2, 0]), [0], [1], 2)),
        View("w2_lines_per_order", GroupAgg("w2o/g", Join("w2o/j", Project("w2o/po", S("w2o", "orders"), [0, 1]), Project("w2o/pl", S("w2o", "lineitem"), [0, 4]), 0, 0), [0], [("COUNT", None), ("SUM", 3)])),
    ]
