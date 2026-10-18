"""Deterministic campaign matrix (Amendment v1.1): every unit has exactly one execution-unit class."""
from __future__ import annotations
import csv, io
from typing import Dict, List
from .campaign import hmac_seed

CLASSES = ("SEARCH_TRIAL", "DETERMINISTIC_SUITE", "MINIMIZATION", "SECONDARY_ORACLE", "ABLATION", "NOT_APPLICABLE")
FIELDS = ["unit_id", "stage", "target", "workload", "tool", "unit_class", "rep", "seed", "budget_kind", "budget_value",
          "required_capabilities", "applicability", "rqs", "est_slot_hours"]


def _hours(budget: dict, est_exec_hours: float) -> float:
    return budget["value"] / 3600.0 if budget["kind"] == "seconds" else budget["value"] * est_exec_hours


def build_matrix(cfg: dict) -> List[dict]:
    m = cfg["matrix"]; ms = cfg["master_seed"]; rows = []
    eh = cfg["duration_gate"]["est_hours_per_execution"]

    def add(stage, target, wl, tool, cls, rep, budget, caps, appl, rqs, est):
        uid = f"{stage}|{target}|{wl}|{tool}|{rep}"
        rows.append({"unit_id": uid, "stage": stage, "target": target, "workload": wl, "tool": tool, "unit_class": cls,
                     "rep": rep, "seed": hmac_seed(ms, stage, target, wl, tool, rep) if rep != "-" else hmac_seed(ms, stage, target, wl, tool),
                     "budget_kind": budget["kind"] if budget else "-", "budget_value": budget["value"] if budget else 0,
                     "required_capabilities": caps, "applicability": appl, "rqs": rqs, "est_slot_hours": round(est, 4)})
    p = cfg["pilot"]
    for rep in range(p["trials"]):
        for wl in p["workloads"]:
            for tg in p["targets"]:
                for tool in p["tools"]:
                    add("pilot", tg, wl, tool, "SEARCH_TRIAL", rep, p["budget"], "views+lifecycle", "APPLICABLE", "pilot-gate", _hours(p["budget"], eh))
    f = cfg["full"]
    for rep in range(f["trials"]):
        for wl in f["workloads"]:
            for tg in f["targets"]:
                for tool in m["search_tools"]:
                    add("full", tg, wl, tool, "SEARCH_TRIAL", rep, f["budget"], "views+lifecycle", "APPLICABLE", "RQ1;RQ3", _hours(f["budget"], eh))
                for tool, spec in sorted(m["ablation_map"].items()):
                    if tg in spec["targets"] and wl in spec["workloads"]:
                        add("full", tg, wl, tool, "ABLATION", rep, f["budget"], "views+lifecycle", "APPLICABLE", ";".join(spec["rqs"]), _hours(f["budget"], eh))
                        if spec.get("matched_seed_of"):            # v1.4: matched control shares the treatment's trial seed
                            rows[-1]["seed"] = hmac_seed(ms, "full", tg, wl, spec["matched_seed_of"], rep)
    for tool, spec in sorted(m["secondary_oracles"].items()):
        for tg in f["targets"]:
            for wl in f["workloads"]:
                add("full", tg, wl, tool, "SECONDARY_ORACLE", "-", {"kind": "checks", "value": spec["checks"]}, "batch-query path",
                    "APPLICABLE", ";".join(spec["rqs"]), spec["est_hours"])
    for tg in f["targets"]:
        spec = m["deterministic_suites"][tg]
        if spec["applicable"]:
            add("full", tg, "-", "baseline_native_suite", "DETERMINISTIC_SUITE", "-", None, "native suite in target image", "APPLICABLE", "RQ1", spec["est_hours"])
        else:
            add("full", tg, "-", "baseline_native_suite", "NOT_APPLICABLE", "-", None, "native suite in target image",
                "NOT_APPLICABLE: " + spec["reason"], "RQ1", 0.0)
    for tg in f["targets"]:
        add("closure", tg, "-", "witness_minimization+ddmin", "MINIMIZATION", "-", None, "same witnesses as S8", "APPLICABLE", "RQ5",
            m["minimization"]["est_hours_per_target"])
    for r in rows:
        assert r["unit_class"] in CLASSES
    return rows


def summarize(rows: List[dict], overhead_hours: float) -> Dict[str, float]:
    c = lambda k: sum(1 for r in rows if r["unit_class"] == k)
    search = sum(r["est_slot_hours"] for r in rows if r["unit_class"] in ("SEARCH_TRIAL", "ABLATION"))
    non = sum(r["est_slot_hours"] for r in rows if r["unit_class"] in ("DETERMINISTIC_SUITE", "MINIMIZATION", "SECONDARY_ORACLE")) + overhead_hours
    return {"TOTAL_UNITS": len(rows), "SEARCH_TRIALS": c("SEARCH_TRIAL"), "DETERMINISTIC_SUITES": c("DETERMINISTIC_SUITE"),
            "MINIMIZATION_UNITS": c("MINIMIZATION"), "SECONDARY_ORACLE_UNITS": c("SECONDARY_ORACLE"), "ABLATION_UNITS": c("ABLATION"),
            "NOT_APPLICABLE_UNITS": c("NOT_APPLICABLE"), "TOTAL_SEARCH_SLOT_HOURS": round(search, 3),
            "TOTAL_NONSEARCH_ESTIMATED_SLOT_HOURS": round(non, 3)}


def to_csv(rows: List[dict]) -> str:
    f = io.StringIO(); w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n"); w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in FIELDS})
    return f.getvalue()


def legacy_v1_0_slot_hours(cfg: dict) -> float:
    """Projected slot-hours of the superseded v1.0 matrix (every full tool x targets x workloads x 10 x 24 h, plus pilot)."""
    p, f = cfg["pilot"], cfg["full"]
    tools = len(cfg["matrix"]["search_tools"]) + len(cfg["matrix"]["ablation_map"]) + len(cfg["matrix"]["secondary_oracles"])
    pilot = p["trials"] * len(p["workloads"]) * len(p["targets"]) * len(p["tools"]) * p["budget"]["value"] / 3600
    return pilot + tools * len(f["targets"]) * len(f["workloads"]) * 10 * 24
