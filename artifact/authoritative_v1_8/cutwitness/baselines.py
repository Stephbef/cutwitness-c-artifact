"""Baselines B3-B8 (B1/B2 and the five ablations live in pipeline.TOOLS)."""
from __future__ import annotations
import random
from typing import Callable, Dict, List, Optional, Tuple
from .model import Life, Txn, ZSet, apply_txn, empty_state, history_digest, is_txn, legal_state, prefix_legal, src, sha
from .oracles import judge, minimize, obs_digest, reference_obs, triage
from .w3 import gen_history, gen_views, _new_row


# ---------------------------------------------------------------- B3 generic stateful SQL fuzzing
def b3_stateful_fuzz_history(rng: random.Random, schema, n: int, lifecycle_kinds) -> List:
    """Grammar-free statement-sequence fuzzing: bursts of inserts, deletes and updates with random lifecycle commands,
    without semantic guidance, equivalence classes or suffixes (sqlsmith-style sequence generation)."""
    h = gen_history(rng, schema, n, max_rows=rng.randint(1, 6))
    for _ in range(rng.randint(0, 2)):
        if lifecycle_kinds:
            h.insert(rng.randrange(len(h) + 1), Life(rng.choice(sorted(lifecycle_kinds))))
    return h


# ---------------------------------------------------------------- B4 Zippy-style
class ZippyModel:
    """Re-implementation of Materialize Zippy's mechanism: random action sequences (insert/delete ranges, restarts)
    validated against an expected state tracked as watermarks (min/max/count of live integer keys) per table."""

    def __init__(self, schema):
        self.schema = schema

    def history(self, rng: random.Random, n: int, lifecycle_kinds) -> List:
        x = empty_state(self.schema); h = []
        for _ in range(n):
            a = rng.random()
            if a < 0.15 and lifecycle_kinds:
                h.append(Life(rng.choice(sorted(lifecycle_kinds)))); continue
            t = rng.choice(self.schema.order)
            live = sorted(x[t].d)
            if a < 0.55 or not live:
                rows = [_new_row(rng, self.schema, x, t)]
                for _k in range(rng.randint(0, 3)):
                    x2 = apply_txn(x, Txn({t: ZSet([(r, 1) for r in rows])}))
                    rows.append(_new_row(rng, self.schema, x2, t))
                txn = Txn({t: ZSet([(r, 1) for r in rows])})
            else:
                k = rng.randint(1, min(4, len(live))); lo = rng.randrange(len(live) - k + 1)
                txn = Txn({t: ZSet([(r, -1) for r in live[lo:lo + k]])})
            x1 = apply_txn(x, txn)
            if legal_state(self.schema, x1)[0]:
                h.append(txn); x = x1
        return h

    @staticmethod
    def watermarks(x, table) -> Tuple[int, Optional[int], Optional[int]]:
        keys = [r[0] for r in x[table].d]
        return len(keys), (min(keys) if keys else None), (max(keys) if keys else None)


def b4_validate(factory, schema, views, h) -> dict:
    """Zippy-style validation: compares maintained view outputs against the expected state model after every action."""
    eng = factory(); x = empty_state(schema)
    for i, e in enumerate(h):
        if is_txn(e):
            eng.apply_transaction(e); x = apply_txn(x, e)
        else:
            eng.lifecycle(e.kind)
        eng.flush()
        if obs_digest(eng.read_views()) != obs_digest(reference_obs(views, x)):
            return {"diverges": True, "at": i}
    return {"diverges": False}


# ---------------------------------------------------------------- B5 target-native suites
NATIVE_SUITES = {  # only targets whose pinned image ships a runnable suite; others are NOT_APPLICABLE in the matrix
    "pg_ivm": {"cmd": ["exec", "-u", "postgres", "-e", "PGPASSWORD=cw", "cw-pgivm-s0", "bash", "-lc",
                       "cd /src/pg_ivm && make installcheck USE_PGXS=1 PGUSER=postgres"], "pass_regex": r"All \d+ tests passed|# All \d+ tests passed"},
}


def b5_run_native(docker, target: str, timeout_s: float) -> dict:
    import re
    if target not in NATIVE_SUITES:
        return {"target": target, "status": "NOT_APPLICABLE", "detail": "no runnable native suite in the pinned image", "new_bugs": 0}
    spec = NATIVE_SUITES[target]
    try:
        out = docker.run(spec["cmd"], timeout_s)
    except Exception as e:
        return {"target": target, "status": "FAILED_TO_RUN", "detail": str(e)[:300], "new_bugs": 0}
    ok = re.search(spec["pass_regex"], out) is not None
    return {"target": target, "status": "PASS" if ok else "FAIL", "tail": out[-400:], "new_bugs": 0 if ok else None}


# ---------------------------------------------------------------- B6 source-level partial-order reduction
def source_fingerprint(schema, h) -> str:
    """Source-level POR: transactions commute iff they touch disjoint (table, primary key) sets; fingerprint = per-row
    sequence of deltas (Mazurkiewicz class over row-level independence), lifecycle events as global barriers."""
    seqs: Dict[str, list] = {}; barrier = 0
    for e in h:
        if not is_txn(e):
            barrier += 1; continue
        for t, r, m in e.rows():
            tb = schema.tables[t]
            key = (t, tuple(r[i] for i in tb.pk) if tb.pk else r)
            seqs.setdefault(sha([t, list(map(str, key[1]))]), []).append([barrier, sha(e.canon()), m])
    return sha(sorted(seqs.items()))


# ---------------------------------------------------------------- B7 query-side metamorphic testing (TLP)
def b7_tlp(query: Callable[[str], list], view, schema, dialect: str, pred_col: int, const) -> dict:
    """Ternary logic partitioning on the target's batch path: Q == Q[p] + Q[NOT p] + Q[p IS NULL] (bag union),
    applied to the view's input subtree (aggregation is recomposed by the reference model)."""
    from .targetsql import _from_clause
    from .refmodel import sql_lit
    top = view.top
    frm, cols, where = _from_clause(top.child if not hasattr(top, "left") else top)
    base = " AND ".join(where) if where else "TRUE"
    e = cols[pred_col]
    q = lambda cond: query(f"SELECT {', '.join(cols)} FROM {frm} WHERE ({base}) AND ({cond})")
    whole = query(f"SELECT {', '.join(cols)} FROM {frm} WHERE {base}")
    parts = q(f"{e} = {sql_lit(const)}") + q(f"NOT ({e} = {sql_lit(const)})") + q(f"({e} = {sql_lit(const)}) IS NULL")
    norm = lambda rows: sorted(map(repr, rows))
    return {"diverges": norm(whole) != norm(parts)}


def tlp_predicate(view, schema, x):
    """Type-aware, deterministic TLP partition predicate: column 0 of the operator input; constant = smallest
    non-NULL value of that column in the current source state (typed default if none)."""
    from decimal import Decimal
    from .refmodel import linear_source
    from .targetsql import col_types
    top = view.top
    child = top if hasattr(top, "left") else top.child
    typ = col_types(child, schema)[0]
    ls = linear_source(child) if not hasattr(child, "left") else linear_source(child.left)
    vals = []
    if ls is not None:
        table, f = ls
        for r in x[table].d:
            y = f(r)
            if y is not None and y[0] is not None:
                vals.append(y[0])
    const = min(vals) if vals else {"int": 1, "dec": Decimal("1"), "text": "a"}[typ]
    return 0, const


# ---------------------------------------------------------------- B8 ddmin (standalone comparison minimizer)
def ddmin(schema, items: List, test: Callable[[List], bool], budget: int = 400, counters: dict = None) -> Tuple[List, int]:
    """Zeller & Hildebrandt ddmin over history events (legality-filtered), returns (1-minimal list, logical test calls).
    `counters["target"]` (if given) receives the number of calls that reached the target."""
    calls = [0]
    if counters is not None:
        counters["target"] = 0

    def t(c):
        calls[0] += 1
        if not (calls[0] <= budget and prefix_legal(schema, c)[0]):
            return False
        if counters is not None:
            counters["target"] += 1
        return test(c)
    n = 2; cur = list(items)
    while len(cur) >= 2:
        size = max(1, len(cur) // n); subsets = [cur[i:i + size] for i in range(0, len(cur), size)]
        reduced = False
        for i, sub in enumerate(subsets):
            if t(sub):
                cur, n, reduced = sub, 2, True; break
            comp = [e for j, s in enumerate(subsets) if j != i for e in s]
            if comp and t(comp):
                cur, n, reduced = comp, max(n - 1, 2), True; break
        if not reduced:
            if n >= len(cur):
                break
            n = min(len(cur), 2 * n)
    return cur, calls[0]
