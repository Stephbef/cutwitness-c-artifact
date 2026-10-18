"""Oracles O1-O4, DuckDB independent reference (O3), ordered triage and minimizer."""
from __future__ import annotations
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple
from .model import Life, Txn, ZSet, apply_txn, empty_state, is_txn, legal_state, prefix_legal, src, sha
from .refmodel import view_sql, view_sql_postprocess, touched
from contextlib import contextmanager


class ExecutionRecorder:
    """Records every history actually executed against a target (Patch-2, observation only: no RNG, no control flow)."""

    def __init__(self, clock):
        self.rows: List[dict] = []
        self.category = "search"
        self.clock = clock


_REC: Optional[ExecutionRecorder] = None


@contextmanager
def recording(rec: ExecutionRecorder):
    global _REC
    prev = _REC; _REC = rec
    try:
        yield rec
    finally:
        _REC = prev


@contextmanager
def category(name: str):
    if _REC is None:
        yield; return
    prev = _REC.category; _REC.category = name
    try:
        yield
    finally:
        _REC.category = prev


def _record(h, suffix, err):
    if _REC is None:
        return None
    from .model import history_digest
    _REC.rows.append({"seq": len(_REC.rows), "category": _REC.category, "executed": True, "history_id": history_digest(h),
                      "suffix_id": history_digest(suffix) if suffix else None, "history_length": len(h),
                      "suffix_length": len(suffix or []), "lifecycle_kinds": [e.kind for e in h if not is_txn(e)],
                      "t": _REC.clock(), "outcome": "ERROR" if err else "EXECUTED"})
    return len(_REC.rows) - 1

NONDET_RERUNS = 10  # frozen: all re-executions must produce identical observations before any bug can be counted
TRIAGE_ORDER = ["INFRASTRUCTURE_ERROR", "UNSUPPORTED_SEMANTICS", "TARGET_NONDETERMINISM", "CANONICALIZATION",
                "REFERENCE_MODEL_BUG", "EXPECTED", "LIFECYCLE_RECOVERY_BUG", "TARGET_MAINTENANCE_BUG"]
SQL_TYPES = {"int": "BIGINT", "dec": "DECIMAL(18,4)", "text": "VARCHAR"}


def reference_obs(views, x) -> Dict[str, ZSet]:
    return {v.name: v.eval(x) for v in views}


def duckdb_obs(schema, views, x) -> Dict[str, ZSet]:
    import duckdb
    con = duckdb.connect(":memory:")
    try:
        for name in schema.order:
            tb = schema.tables[name]
            con.execute(f"CREATE TABLE {name} (" + ", ".join(f"c{i} {SQL_TYPES[t]}" for i, (_, t, _) in enumerate(tb.cols)) + ")")
            rows = [r for r, m in x[name].items_sorted() for _ in range(m)]
            if rows:
                con.executemany(f"INSERT INTO {name} VALUES (" + ", ".join("?" for _ in tb.cols) + ")", [list(r) for r in rows])
        out = {}
        for v in views:
            res = con.execute(view_sql(v)).fetchall()
            out[v.name] = view_sql_postprocess(v, res)
        return out
    finally:
        con.close()


def obs_digest(obs: Dict[str, ZSet]) -> str:
    return sha({k: obs[k].canon() for k in sorted(obs)})


def execute(factory: Callable, h: List, suffix: Optional[List] = None):
    """Run h (then suffix steps) on a fresh target; return (obs_at_cut, [obs after each suffix step], error)."""
    res = _execute(factory, h, suffix)
    _record(h, suffix, res[2])
    return res


def _execute(factory: Callable, h: List, suffix: Optional[List] = None):
    eng = None
    try:
        eng = factory()
        for e in h:
            if is_txn(e):
                eng.apply_transaction(e)
            else:
                eng.lifecycle(e.kind)
        eng.flush()
        at_cut = eng.read_views()
        steps = []
        for t in suffix or []:
            eng.apply_transaction(t); eng.flush(); steps.append(eng.read_views())
        return at_cut, steps, None
    except Exception as ex:  # recorded, classified as infrastructure error by triage
        return None, None, f"{type(ex).__name__}: {ex}"
    finally:
        if eng is not None and hasattr(eng, "destroy"):
            try:
                eng.destroy()
            except Exception:
                pass


def judge(factory, schema, views, h: List, suffix: Optional[List] = None, use_o3: bool = True) -> dict:
    """O1 (clean rebuild + reference), O4 (per-step continuation); O3 cross-check of the reference."""
    at_cut, steps, err = execute(factory, h, suffix)
    row = (len(_REC.rows) - 1) if _REC is not None else None
    if err:
        return {"diverges": True, "error": err, "where": "infra"}
    x = src(schema, h)
    ref = reference_obs(views, x)
    v = {"diverges": False, "o1_cut": obs_digest(at_cut) == obs_digest(ref), "o4_steps": [], "error": None,
         "obs_digest": obs_digest(at_cut), "step_digests": [obs_digest(o) for o in (steps or [])]}
    if use_o3:
        v["o3_agree"] = obs_digest(duckdb_obs(schema, views, x)) == obs_digest(ref)
    if not v["o1_cut"]:
        v["diverges"] = True; v["where"] = "cut"
    cur = x
    for i, (t, o) in enumerate(zip(suffix or [], steps or [])):
        cur = apply_txn(cur, t)
        ok = obs_digest(o) == obs_digest(reference_obs(views, cur))
        v["o4_steps"].append(ok)
        if not ok and not v["diverges"]:
            v["diverges"] = True; v["where"] = f"suffix:{i}"
    if row is not None:
        _REC.rows[row]["outcome"] = ("DIVERGE_" + v["where"].split(":")[0].upper()) if v["diverges"] else "PASS"
    return v


def path_vs_path(factory, h1: List, h2: List) -> bool:
    a, _, e1 = execute(factory, h1); b, _, e2 = execute(factory, h2)
    if e1 or e2:
        return True
    return obs_digest(a) != obs_digest(b)


def triage(factory, schema, views, h: List, suffix=None, caps=None) -> dict:
    """Ordered triage; only LIFECYCLE_RECOVERY_BUG / TARGET_MAINTENANCE_BUG can become candidate bugs."""
    rec = {"history_len": len(h), "suffix_len": len(suffix or [])}
    v1 = judge(factory, schema, views, h, suffix)
    if v1.get("error"):
        return {**rec, "class": "INFRASTRUCTURE_ERROR", "detail": v1["error"], "candidate": False}
    if caps is not None:
        kinds = {e.kind for e in h if not is_txn(e)}
        if not kinds <= set(caps["lifecycle"]) or any(v.top.kind not in caps["ops"] for v in views):
            return {**rec, "class": "UNSUPPORTED_SEMANTICS", "candidate": False}
    if not v1["diverges"]:
        return {**rec, "class": "NO_DIVERGENCE", "candidate": False}
    sigs = {(v1["obs_digest"], tuple(v1["step_digests"]))}   # the triggering execution is part of the identity check
    for _ in range(NONDET_RERUNS):
        a, sa, err = execute(factory, h, suffix)
        if err:
            return {**rec, "class": "INFRASTRUCTURE_ERROR", "detail": err, "candidate": False}
        sigs.add((obs_digest(a), tuple(obs_digest(o) for o in sa)))
    if len(sigs) > 1:
        return {**rec, "class": "TARGET_NONDETERMINISM", "candidate": False, "distinct_outcomes": len(sigs)}
    x = src(schema, h)
    ref = reference_obs(views, x); o3 = duckdb_obs(schema, views, x)
    if obs_digest(ref) != obs_digest(o3):
        return {**rec, "class": "REFERENCE_MODEL_BUG", "candidate": False}
    v2 = judge(factory, schema, views, h, suffix)
    reproductions = int(v1["diverges"]) + int(v2["diverges"])
    lifecycle = [e for e in h if not is_txn(e)]
    if lifecycle:
        stripped = [e for e in h if is_txn(e)]
        s1 = judge(factory, schema, views, stripped, suffix); s2 = judge(factory, schema, views, stripped, suffix)
        if not s1["diverges"] and not s2["diverges"]:
            return {**rec, "class": "LIFECYCLE_RECOVERY_BUG", "reproductions": reproductions,
                    "candidate": reproductions >= 2, "where": v1.get("where")}
    return {**rec, "class": "TARGET_MAINTENANCE_BUG", "reproductions": reproductions,
            "candidate": reproductions >= 2, "where": v1.get("where")}


# ---------------------------------------------------------------- minimizer

def minimize(schema, views, h: List, suffix: List, pred: Callable[[List, List], bool], budget: int = 400):
    """Slice-1-minimal witness search: key slicing, inverse pairs, lifecycle, suffix, rows, ddmin fallback."""
    trace = []
    calls = [0]
    target_calls = [0]

    def ok(hh, ss):
        calls[0] += 1
        if calls[0] > budget:
            return False
        good, _, _ = prefix_legal(schema, hh + ss)
        if not good:
            return False
        target_calls[0] += 1
        return pred(hh, ss)

    cur, suf = list(h), list(suffix)
    # 1. suffix minimization: shortest prefix of the suffix that still diverges
    for n in range(0, len(suf) + 1):
        if ok(cur, suf[:n]):
            if n < len(suf):
                trace.append({"step": "suffix", "from": len(suf), "to": n})
            suf = suf[:n]; break
    # 2. lifecycle minimization
    i = 0
    while i < len(cur):
        if not is_txn(cur[i]):
            cand = cur[:i] + cur[i + 1:]
            if ok(cand, suf):
                trace.append({"step": "lifecycle", "removed": i}); cur = cand; continue
        i += 1
    # 3. inverse-pair elimination
    changed = True
    while changed:
        changed = False
        for a in range(len(cur)):
            if not is_txn(cur[a]):
                continue
            inv = cur[a].inverse().canon()
            for b in range(a + 1, len(cur)):
                if is_txn(cur[b]) and cur[b].canon() == inv:
                    cand = cur[:a] + cur[a + 1:b] + cur[b + 1:]
                    if ok(cand, suf):
                        trace.append({"step": "inverse_pair", "removed": [a, b]}); cur = cand; changed = True
                    break
            if changed:
                break
    # 4. ddmin over events (complement removal)
    n = 2
    while len(cur) >= 2:
        chunk = max(1, len(cur) // n); reduced = False
        for s in range(0, len(cur), chunk):
            cand = cur[:s] + cur[s + chunk:]
            if cand and ok(cand, suf):
                trace.append({"step": "ddmin", "removed": [s, s + chunk]}); cur = cand; n = max(n - 1, 2); reduced = True; break
        if not reduced:
            if n >= len(cur):
                break
            n = min(len(cur), n * 2)
    # 5. row minimization inside transactions
    for i in range(len(cur)):
        if not is_txn(cur[i]):
            continue
        rows = list(cur[i].rows())
        j = 0
        while len(rows) > 1 and j < len(rows):
            keep = rows[:j] + rows[j + 1:]
            d = {}
            for t, r, m in keep:
                d.setdefault(t, ZSet()).add_row(r, m)
            cand = cur[:i] + [Txn(d)] + cur[i + 1:]
            if ok(cand, suf):
                trace.append({"step": "row", "txn": i}); cur = cand; rows = keep; continue
            j += 1
    # 6. fixpoint: single-event and single-row removal until 1-minimal (or budget exhausted)
    changed = True
    while changed and calls[0] <= budget:
        changed = False
        for i in range(len(cur)):
            cand = cur[:i] + cur[i + 1:]
            if cand and ok(cand, suf):
                trace.append({"step": "single_event", "removed": i}); cur = cand; changed = True; break
        if changed:
            continue
        for i in range(len(cur)):
            if not is_txn(cur[i]):
                continue
            rows = list(cur[i].rows())
            for j in range(len(rows)):
                if len(rows) < 2:
                    break
                d = {}
                for t, r, m in rows[:j] + rows[j + 1:]:
                    d.setdefault(t, ZSet()).add_row(r, m)
                cand = cur[:i] + [Txn(d)] + cur[i + 1:]
                if ok(cand, suf):
                    trace.append({"step": "single_row", "txn": i}); cur = cand; changed = True; break
            if changed:
                break
    # certificate: no single event / row removal keeps divergence and legality
    cert = {"slice_1_minimal": True, "checked_events": len(cur), "budget_exhausted": calls[0] > budget}
    counters = {"logical": None, "target": None}
    for i in range(len(cur)):
        cand = cur[:i] + cur[i + 1:]
        if cand and ok(cand, suf):
            cert["slice_1_minimal"] = False; cert["counterexample_index"] = i; break
    for n in range(len(suf)):
        if ok(cur, suf[:n]):
            cert["slice_1_minimal"] = False; cert["suffix_shorter"] = n; break
    cert["predicate_calls_logical"] = calls[0]; cert["predicate_calls_target"] = target_calls[0]
    return cur, suf, trace, cert
