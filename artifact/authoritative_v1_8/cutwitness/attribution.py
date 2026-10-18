"""Latent-state attribution (Amendment v1.2).

Evidence classification after candidate discovery (stage S8): for every reproducible latent witness
(FC(h) holds, the characterization continuation c fails), replay
  E1: h followed by c, and
  E2: a fresh instance loaded with exactly src(h) in one transaction (no history, no lifecycle), followed by the same c.
  E3 (Amendment v1.6): a fresh instance that reaches exactly src(h) through a canonical incremental history (inserts only,
      parent tables first, rows in canonical order, one row per transaction, independent of h), followed by the same c.
E1 fails, E2 passes and E3 passes      -> HISTORY_CONDITIONED_LATENT (detail STRONG_HISTORY_CONDITIONED): the original
                                          incremental path matters beyond both a bulk and a canonical incremental reconstruction;
E1 fails, E2 fails and E3 fails        -> CONTINUATION_TRIGGERED (real failure; no claim that h corrupted state);
E2 and E3 disagree                     -> UNRESOLVED_ATTRIBUTION (detail PATH_CONSTRUCTION_SENSITIVE);
anything else, or non-identical replays -> UNRESOLVED_ATTRIBUTION.
It never influences search, scheduling, treatment, seeds, budgets, triage or pilot criteria.
"""
from __future__ import annotations
import json, os
from typing import Callable, Dict, List
from .campaign import atomic_write
from .model import Txn, ZSet, apply_txn, cjson, empty_state, history_digest, history_from_canon, is_txn, legal_state, sha, src
from .oracles import judge
from .serialize import schema_from_json, views_from_json

CLASSES = ("HISTORY_CONDITIONED_LATENT", "CONTINUATION_TRIGGERED", "UNRESOLVED_ATTRIBUTION")


def fresh_load(schema, h: List) -> List:
    """src(h) as a single legal transaction (parents first is guaranteed by the adapters' statement order)."""
    x = src(schema, h)
    delta = {t: x[t] for t in schema.order if x[t]}
    return [Txn(delta)] if delta else []


def canonical_history(schema, h: List):
    """E3 path: src(h) reached through normal incremental insert transactions, deterministic and independent of h.
    Returns (transactions, independent_of_h, legal_every_prefix)."""
    x = src(schema, h)
    def build(rev):
        rows = []
        for t in schema.order:                                  # parent tables first (FK legality)
            rs = [r for r, m in x[t].items_sorted() for _ in range(m)]
            rows += [(t, r) for r in (list(reversed(rs)) if rev else rs)]
        return [Txn({t: ZSet([(r, 1)])}) for t, r in rows]
    orig = [e.canon() for e in h if is_txn(e)]
    txns = build(False); independent = [t.canon() for t in txns] != orig
    if not independent:
        txns = build(True); independent = [t.canon() for t in txns] != orig
    cur = empty_state(schema); legal = True
    for t in txns:
        cur = apply_txn(cur, t); legal = legal and legal_state(schema, cur)[0]
    return txns, independent, legal and cur == x


def _replay(fac, schema, views, hist, suffix) -> dict:
    v = judge(fac, schema, views, hist, suffix, use_o3=False)
    return {"error": v.get("error"), "fc_at_cut": bool(v.get("o1_cut")), "where": v.get("where") if v["diverges"] else "PASS",
            "obs": v.get("obs_digest"), "steps": list(v.get("step_digests", []))}


def _summary(r: dict) -> str:
    if r["error"]:
        return "ERROR"
    cut = "FC_PASS" if r["fc_at_cut"] else "FC_FAIL"
    tail = "CONTINUATION_PASS" if r["where"] == "PASS" else f"CONTINUATION_FAIL@{r['where']}"
    return f"{cut};{tail}"


def attribute(fac: Callable, schema, views, h: List, suffix: List, replays: int) -> dict:
    e1 = [_replay(fac, schema, views, h, suffix) for _ in range(replays)]
    fl = fresh_load(schema, h)
    e2 = [_replay(fac, schema, views, fl, suffix) for _ in range(replays)]
    ch, independent, legal = canonical_history(schema, h)
    e3 = [_replay(fac, schema, views, ch, suffix) for _ in range(replays)] if legal else []
    k = lambda r: json.dumps(r, sort_keys=True, default=str)
    detail = None
    if len({k(r) for r in e1}) > 1 or len({k(r) for r in e2}) > 1 or len({k(r) for r in e3}) > 1:
        cls, reason = "UNRESOLVED_ATTRIBUTION", "non-identical replays (nondeterminism)"
    elif any(r["error"] for r in e1 + e2 + e3):
        cls, reason = "UNRESOLVED_ATTRIBUTION", "infrastructure error during replay"
    elif not (e1[0]["fc_at_cut"] and str(e1[0]["where"]).startswith("suffix")):
        cls, reason = "UNRESOLVED_ATTRIBUTION", "history path is not latent on replay"
    elif not e2[0]["fc_at_cut"]:
        cls, reason = "UNRESOLVED_ATTRIBUTION", "fresh load of the final cut fails at the cut"
    elif not legal or not e3:
        cls, reason = "UNRESOLVED_ATTRIBUTION", "canonical incremental reconstruction of the final cut is not legal"
    elif not e3[0]["fc_at_cut"]:
        cls, reason = "UNRESOLVED_ATTRIBUTION", "canonical incremental reconstruction fails at the cut"
    elif not independent:
        cls, reason = "UNRESOLVED_ATTRIBUTION", "canonical reconstruction coincides with the original history"
    else:
        p2, p3 = e2[0]["where"] == "PASS", e3[0]["where"] == "PASS"
        if p2 and p3:
            cls, detail = "HISTORY_CONDITIONED_LATENT", "STRONG_HISTORY_CONDITIONED"
            reason = "continuation fails only after the original path; bulk (E2) and canonical incremental (E3) reconstructions pass"
        elif not p2 and not p3:
            cls, detail = "CONTINUATION_TRIGGERED", "CONTINUATION_TRIGGERED"
            reason = "continuation also fails from both clean reconstructions (E2 bulk, E3 canonical incremental)"
        else:
            cls, detail = "UNRESOLVED_ATTRIBUTION", "PATH_CONSTRUCTION_SENSITIVE"
            reason = f"E2 {'passes' if p2 else 'fails'} but E3 {'passes' if p3 else 'fails'}: reconstructions disagree"
    return {"final_cut_digest": sha(fl[0].canon()) if fl else sha([]), "continuation_digest": history_digest(suffix),
            "history_path_result": _summary(e1[0]), "fresh_cut_result": _summary(e2[0]),
            "canonical_path_result": _summary(e3[0]) if e3 else "NOT_RUN", "canonical_transactions": len(ch),
            "canonical_independent_of_history": independent, "attribution_class": cls, "attribution_detail": detail or cls,
            "reason": reason, "replays_per_path": replays, "attribution_protocol": "E1/E2/E3 (Amendment v1.6)"}


def attribution_closure(cfg: dict, run_dir: str, witnesses: List[dict], make_factory: Callable) -> Dict[str, dict]:
    adir = os.path.join(run_dir, "attribution"); os.makedirs(adir, exist_ok=True); out = {}
    for w in sorted(witnesses, key=lambda z: z["id"]):
        if not (w.get("latent") and w.get("status") == "NEW" and "original_history" in w):
            continue
        p = os.path.join(adir, f"{w['id']}.json")
        if os.path.exists(p):                                     # resumable per witness
            out[w["id"]] = json.load(open(p)); continue
        sch = schema_from_json(w["schema"]); views = views_from_json(sch, w["views"])
        fac, _ = make_factory(cfg, w["target"], sch, views, 0)
        rec = {"witness_id": w["id"], "target": w["target"], "workload": w["workload"],
               **attribute(fac, sch, views, history_from_canon(w["original_history"]), history_from_canon(w["original_suffix"]),
                           cfg["nondet_reruns"])}
        atomic_write(p, cjson(rec).encode()); out[w["id"]] = rec
    return out
