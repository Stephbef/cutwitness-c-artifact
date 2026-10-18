"""Frozen pilot decision engine (signals A-D). No human interpretation, no redesign path."""
from __future__ import annotations
from statistics import median
from typing import Dict, List
from .stats import a12

CANDIDATE_CLASSES = ("LIFECYCLE_RECOVERY_BUG", "TARGET_MAINTENANCE_BUG")
CW = "cutwitness_c"


def _cands(u):
    return [d for d in u.get("divergences", []) if d["triage"].get("candidate") and d["triage"]["class"] in CANDIDATE_CLASSES]


def _ttfd(u, budget):
    v = u.get("first_candidate_at")
    return (budget, 0) if v is None else (v, 1)


def evaluate(units: List[dict], planned: int, sig: dict, budget: float, baselines: List[str], targets: List[str]) -> dict:
    """units: committed pilot unit results. planned: number of planned pilot units."""
    if len(units) < planned:
        return {"decision": "INCOMPLETE", "reason": f"{planned - len(units)} pilot units not committed", "signals": {}}
    cw = [u for u in units if u["tool"] == CW]
    base = [u for u in units if u["tool"] in baselines]
    # A: at least one class-7/8 candidate (including latent ones) found by CutWitness-C
    A = sum(len(_cands(u)) for u in cw) >= sig["A"]
    # B: >= B_speedup x faster median time to first candidate than the best baseline, A12 >= B_a12, on every pilot target
    B_per = {}
    for t in targets:
        c = [_ttfd(u, budget)[0] for u in cw if u["target"] == t]
        bests = []
        for b in baselines:
            xs = [_ttfd(u, budget)[0] for u in base if u["target"] == t and u["tool"] == b]
            if xs:
                bests.append((median(xs), xs, b))
        if not c or not bests or all(_ttfd(u, budget)[1] == 0 for u in cw if u["target"] == t):
            B_per[t] = False; continue
        mb, xs, _ = min(bests, key=lambda z: z[0])
        B_per[t] = (median(c) * sig["B_speedup"] <= mb) and a12(xs, c) >= sig["B_a12"]
    B = bool(B_per) and all(B_per.values())
    # C: a divergence class (latent or lifecycle) found by CutWitness-C that no baseline finds in any trial
    def classes(us):
        out = set()
        for u in us:
            for d in _cands(u):
                if d.get("latent"):
                    out.add("latent")
                if d["triage"]["class"] == "LIFECYCLE_RECOVERY_BUG":
                    out.add("lifecycle")
        return out
    C = bool(classes(cw) - classes(base))
    # D: >= ratio x realizable k-word coverage at equal budget without fewer candidate divergences, vs every baseline
    cov = lambda us: median([sum(u.get("coverage", {}).values()) for u in us]) if us else 0
    n_c = lambda us: sum(len(_cands(u)) for u in us)
    D = bool(cw) and bool(base)
    for b in baselines:
        bu = [u for u in base if u["tool"] == b]
        if not bu:
            continue
        if not (cov(cw) >= sig["D_coverage_ratio"] * max(cov(bu), 1e-9) and n_c(cw) >= n_c(bu)):
            D = False
    signals = {"A": A, "B": B, "B_per_target": B_per, "C": C, "D": D}
    go = A or B or C or D
    return {"decision": "GO" if go else "PILOT_NO_GO", "signals": signals}
