"""Frozen analysis: RQ tables, bug ledger, coverage, survival, lifecycle, latent, minimization; CSV/Markdown/SVG."""
from __future__ import annotations
import csv, io, json, os
from statistics import median
from typing import Dict, List
from .campaign import atomic_write
from .model import cjson
from .stats import a12, bootstrap_ci, holm, kaplan_meier, logrank, mann_whitney, ratio_of_medians
from . import svgplot

CAND = ("LIFECYCLE_RECOVERY_BUG", "TARGET_MAINTENANCE_BUG")


def _csv(rows: List[dict]) -> str:
    if not rows:
        return ""
    f = io.StringIO(); w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    return f.getvalue()


def analyze(units: List[dict], cfg: dict, label: str, budget: float, out: str, witnesses: List[dict]) -> dict:
    os.makedirs(out, exist_ok=True)
    tools = sorted({u["tool"] for u in units if u.get("unit_class", "SEARCH_TRIAL") in ("SEARCH_TRIAL", "ABLATION", "SECONDARY_ORACLE")})
    targets = sorted({u["target"] for u in units})
    suites = [{"label": label, "target": u["target"], "status": u.get("suite_status")} for u in units if u.get("unit_class") == "DETERMINISTIC_SUITE"]
    units = [u for u in units if u.get("unit_class", "SEARCH_TRIAL") != "DETERMINISTIC_SUITE"]
    st = cfg["statistics"]
    w = lambda name, text: atomic_write(os.path.join(out, name), text.encode())
    hdr = f"# {label}\n"
    # RQ1 bug table
    rq1 = []
    for t in targets:
        for tool in tools:
            us = [u for u in units if u["target"] == t and u["tool"] == tool]
            ds = [d for u in us for d in u["divergences"]]
            rq1.append({"label": label, "target": t, "tool": tool, "trials": len(us),
                        "maintenance": sum(1 for d in ds if d["triage"].get("candidate") and d["triage"]["class"] == CAND[1]),
                        "lifecycle": sum(1 for d in ds if d["triage"].get("candidate") and d["triage"]["class"] == CAND[0]),
                        "latent": sum(1 for d in ds if d["triage"].get("candidate") and d.get("latent")),
                        "unresolved_or_other": sum(1 for d in ds if not d["triage"].get("candidate"))})
    w("rq1_bugs.csv", _csv(rq1))
    w("rq1_native_suites.csv", _csv(suites) if suites else "label,target,status\n")
    # RQ3 survival + comparisons vs CutWitness-C (primary comparisons: cw vs each baseline, per target)
    comps, curves = [], {}
    for t in targets:
        def tt(tool):
            us = [u for u in units if u["target"] == t and u["tool"] == tool]
            return [u["first_candidate_at"] if u["first_candidate_at"] is not None else budget for u in us], \
                   [0 if u["first_candidate_at"] is None else 1 for u in us]
        cw_t, cw_e = tt("cutwitness_c")
        for tool in tools:
            x, e = tt(tool)
            curves[f"{t}:{tool}"] = kaplan_meier(x, e) if x else []
            if tool == "cutwitness_c" or not x or not cw_t or tool not in cfg["matrix"]["search_tools"]:
                continue
            comps.append({"label": label, "target": t, "baseline": tool, "a12_baseline_slower": a12(x, cw_t),
                          "ratio_medians_cw_over_baseline": ratio_of_medians(cw_t, x),
                          "cw_median_ci": list(bootstrap_ci(cw_t, n=st["bootstrap_resamples"], seed=st["bootstrap_seed"])),
                          "mann_whitney_p": mann_whitney(cw_t, x), "logrank_p": logrank(cw_t, cw_e, x, e)})
    # Frozen multiplicity rule: Holm correction is a separate family per target.
    # Never allow comparisons from another target into this target's five-baseline family.
    for t in targets:
        group = [c for c in comps if c["target"] == t]
        adj = holm([c["mann_whitney_p"] for c in group]) if group else []
        for c, a in zip(group, adj):
            c["holm_p"] = a
    w("rq3_comparisons.csv", _csv(comps))
    for t in targets:
        w(f"fig_survival_{t}.svg", svgplot.steps(f"Time to first candidate divergence ({t})",
                                                  {k.split(":", 1)[1]: v for k, v in curves.items() if k.startswith(t + ":")}, budget, label))
    # coverage, latent, lifecycle, minimization
    cov = {tool: median([sum(u.get("coverage", {}).values()) for u in units if u["tool"] == tool] or [0]) for tool in tools}
    w("rq3_coverage.csv", _csv([{"label": label, "tool": k, "median_k_windows": v} for k, v in sorted(cov.items())]))
    w("fig_coverage.svg", svgplot.bars("Median realized k-transition windows per trial", cov, label))
    # ANALYSIS_SPEC_v4: a latent witness requires an executed characterization suffix; arms without one are N/A by design
    lat = {tool: sum(1 for u in units if u["tool"] == tool for d in u["divergences"] if d.get("latent") and d["triage"].get("candidate"))
           for tool in tools if latent_endpoint_applicable(tool)}
    rows2 = [{"label": label, "tool": k, "latent_candidates": lat[k] if k in lat else NA_LATENT} for k in sorted(tools)]
    w("rq2_latent.csv", _csv(rows2))
    w("fig_latent.svg", svgplot.bars("Latent (suffix-stage) candidate divergences; suffix-free arms N/A", lat, label))
    lc = {tool: sum(1 for u in units if u["tool"] == tool for d in u["divergences"] if d["triage"].get("class") == CAND[0]) for tool in tools}
    w("rq4_lifecycle.csv", _csv([{"label": label, "tool": k, "lifecycle_candidates": v} for k, v in sorted(lc.items())]))
    w("fig_lifecycle.svg", svgplot.bars("Lifecycle/recovery candidates", lc, label))
    mins = [{"label": label, "witness": wi["id"], "original_len": wi["original_len"], "minimized_len": wi["minimized_len"],
             "ddmin_len": wi.get("ddmin_len"), "ddmin_calls": wi.get("ddmin_calls"), "status": wi["status"]} for wi in witnesses]
    w("rq5_minimization.csv", _csv(mins))
    w("fig_minimization.svg", svgplot.bars("Witness length after minimization", {m["witness"][:10]: m["minimized_len"] for m in mins} or {"none": 0}, label))
    ledger = [{"label": label, "witness": wi["id"], "target": wi["target"], "class": wi["class"], "signature": wi["signature"],
               "status": wi["status"]} for wi in witnesses]
    w("bug_ledger.csv", _csv(ledger))
    evidence_outputs(units, cfg, label, budget, w, witnesses)
    rq2b_status = rq2b_outputs(units, cfg, label, budget, w)
    if cfg["matrix"]["ablation_map"].get(DELMATCH_CONTROL):
        rq2c_status = rq2b_outputs(units, cfg, label, budget, w, control=DELMATCH_CONTROL, prefix="rq2c")
    rho_outputs(units, label, w)
    summary = {"label": label, "units": len(units), "rq2b_status": rq2b_status, "tools": tools, "targets": targets, "comparisons": len(comps),
               "candidates": sum(r["maintenance"] + r["lifecycle"] for r in rq1), "witnesses": len(witnesses)}
    w("analysis_summary.json", cjson(summary))
    w("README.md", hdr + "\nAll tables and figures in this directory were generated by frozen scripts.\n")
    return summary



# ---------------------------------------------------------------- latent endpoint applicability (ANALYSIS_SPEC_v4)
NA_LATENT = "N/A - arm executes no characterization suffix"


def latent_endpoint_applicable(tool: str) -> bool:
    """A latent witness needs an executed characterization suffix; tools whose suffix stage is off cannot emit one."""
    from .pipeline import TOOLS
    return bool(TOOLS.get(tool, {}).get("suffix"))


# ---------------------------------------------------------------- Patch-2 evidence producers (ANALYSIS_SPEC_v2)
CTX = ("unit_id", "target", "workload", "tool", "trial", "seed")


def _rows_csv(rows, cols):
    f = io.StringIO(); wr = csv.DictWriter(f, fieldnames=cols, lineterminator="\n", extrasaction="ignore"); wr.writeheader()
    for r in rows:
        wr.writerow({c: r.get(c) for c in cols})
    return f.getvalue()


def primary_class(wit) -> str:
    if wit.get("class") == "LIFECYCLE_RECOVERY_BUG":
        return "lifecycle-sensitive"
    if wit.get("latent"):
        return "latent-continuation"
    if wit.get("where") == "path-vs-path":
        return "path-convergence"
    return "final-cut"


def _times(us, key, budget):
    return [u[key] if u.get(key) is not None else budget for u in us], [0 if u.get(key) is None else 1 for u in us]


def _lc_rate(u):
    ev = u.get("lifecycle_events_executed", 0)
    n = sum(1 for d in u.get("divergences", []) if d["triage"].get("candidate") and d["triage"]["class"] == CAND[0])
    return (1000.0 * n / ev) if ev else 0.0


def evidence_outputs(units, cfg, label, budget, w, witnesses):
    search = [u for u in units if u.get("unit_class", "SEARCH_TRIAL") in ("SEARCH_TRIAL", "ABLATION")]
    he = []
    for u in search:
        for r in u.get("execution_log", []):
            he.append({**{k: u.get(k) for k in CTX}, "method": u["tool"], "history_id": r["history_id"], "history_length": r["history_length"],
                       "executed": r["executed"], "category": r["category"], "exec_index": r["seq"], "timestamp": r["t"], "outcome": r["outcome"]})
    w("histories_executed.csv", _rows_csv(he, ["unit_id", "target", "workload", "method", "trial", "seed", "history_id", "history_length",
                                                "executed", "category", "exec_index", "timestamp", "outcome"]))
    agg = []
    for u in search:
        lg = u.get("execution_log", [])
        c = lambda cat, ex: sum(1 for r in lg if r["category"] == cat and r["executed"] == ex)
        agg.append({**{k: u.get(k) for k in CTX}, "method": u["tool"], "executed_search": c("search", True), "executed_path_pair": c("path_pair", True),
                    "executed_triage": c("triage", True), "executed_minimization": c("minimization", True),
                    "pruned_equivalent": sum(1 for r in lg if r["outcome"] == "PRUNED_EQUIVALENT"),
                    "not_selected": sum(1 for r in lg if r["outcome"] == "NOT_SELECTED"), "histories_executed": u.get("histories_executed")})
    w("histories_executed_summary.csv", _rows_csv(agg, ["unit_id", "target", "workload", "method", "trial", "seed", "histories_executed",
                                                         "executed_search", "executed_path_pair", "executed_triage", "executed_minimization",
                                                         "pruned_equivalent", "not_selected"]))
    lat = []
    for u in search:
        ok = latent_endpoint_applicable(u["tool"])
        lat.append({**{k: u.get(k) for k in CTX}, "method": u["tool"], "trial_start": 0,
                    "latent_endpoint": "APPLICABLE" if ok else "NOT_APPLICABLE_BY_DESIGN",
                    "first_latent_time": (u.get("first_latent_candidate_at") if u.get("first_latent_candidate_at") is not None else budget) if ok else NA_LATENT,
                    "censored": (u.get("first_latent_candidate_at") is None) if ok else NA_LATENT,
                    "witness_id": u.get("first_latent_witness") if ok else "", "budget": budget, "time_unit": u.get("budget_kind")})
    w("latent_ttf_event.csv", _rows_csv(lat, ["unit_id", "target", "workload", "method", "trial", "seed", "trial_start", "latent_endpoint",
                                              "first_latent_time", "censored", "witness_id", "budget", "time_unit"]))
    lce = []
    for u in search:
        for r in u.get("execution_log", []):
            if r["executed"] and r["category"] == "search":
                for e in r.get("lifecycle_events", []):
                    lce.append({**{k: u.get(k) for k in CTX}, "method": u["tool"], "history_id": r["history_id"], "event_type": e["type"],
                                "position": e["position"], "placement": e["placement"], "support": e["support"]})
    w("lifecycle_events.csv", _rows_csv(lce, ["unit_id", "target", "workload", "method", "trial", "seed", "history_id", "event_type",
                                              "position", "placement", "support"]))
    rates = []
    for t in sorted({u["target"] for u in search}):
        for tool in sorted({u["tool"] for u in search}):
            us = [u for u in search if u["target"] == t and u["tool"] == tool]
            ev = sum(u.get("lifecycle_events_executed", 0) for u in us)
            n = sum(1 for u in us for d in u.get("divergences", []) if d["triage"].get("candidate") and d["triage"]["class"] == CAND[0])
            rates.append({"label": label, "target": t, "method": tool, "lifecycle_events_executed": ev,
                          "reproducible_lifecycle_divergences": n, "per_1000_events": round(1000.0 * n / ev, 4) if ev else None})
    w("rq4_lifecycle_rates.csv", _rows_csv(rates, ["label", "target", "method", "lifecycle_events_executed", "reproducible_lifecycle_divergences", "per_1000_events"]))
    mc = [{"witness_id": wi["id"], **m} for wi in witnesses for m in wi.get("minimizers", [])]
    for m in mc:
        m["predicate_calls"] = m.get("predicate_calls_target")
    w("minimizer_calls.csv", _rows_csv(mc, ["witness_id", "algorithm", "original_length", "final_length", "predicate_calls",
                                            "predicate_calls_logical", "wall_time_s", "replay_success"]))
    # ablation families (frozen in ANALYSIS_SPEC_v2 via cfg["analysis_spec"])
    st = cfg["statistics"]; comps = []
    for abl, fam in sorted(cfg["analysis_spec"]["ablation_families"].items()):
        cells = cfg["matrix"]["ablation_map"].get(abl)
        if not cells or not fam.get("inferential", True) or fam.get("paired"):   # v4 descriptive; v6 paired families have their own owner
            continue
        group = []
        for t in cells["targets"]:
            cw = [u for u in search if u["tool"] == "cutwitness_c" and u["target"] == t and u["workload"] in cells["workloads"]]
            ab = [u for u in search if u["tool"] == abl and u["target"] == t and u["workload"] in cells["workloads"]]
            if not cw or not ab:
                continue
            row = {"label": label, "family": abl, "rq": fam["rq"], "target": t, "metric": fam["primary_metric"], "n_cw": len(cw), "n_ablation": len(ab)}
            if fam["primary_metric"] in ("latent_ttf", "candidate_ttf"):
                key = "first_latent_candidate_at" if fam["primary_metric"] == "latent_ttf" else "first_candidate_at"
                xc, ec = _times(cw, key, budget); xa, ea = _times(ab, key, budget)
                row.update({"a12": a12(xa, xc), "a12_direction": "P(ablation time > CutWitness-C time)", "mann_whitney_p": mann_whitney(xc, xa),
                            "logrank_p": logrank(xc, ec, xa, ea), "events_cw": sum(ec), "events_ablation": sum(ea)})
            else:
                rc = [_lc_rate(u) for u in cw]; ra = [_lc_rate(u) for u in ab]
                row.update({"a12": a12(rc, ra), "a12_direction": "P(CutWitness-C rate > ablation rate)", "mann_whitney_p": mann_whitney(rc, ra),
                            "logrank_p": None, "events_cw": None, "events_ablation": None})
            group.append(row)
        for r, a in zip(group, holm([r["mann_whitney_p"] for r in group]) if group else []):
            r["holm_p_within_family"] = a
        comps += group
    w("rq_ablation_comparisons.csv", _rows_csv(comps, ["label", "family", "rq", "target", "metric", "n_cw", "n_ablation", "a12", "a12_direction",
                                                        "mann_whitney_p", "holm_p_within_family", "logrank_p", "events_cw", "events_ablation"]))
    for t in sorted({u["target"] for u in search}):
        curves = {}
        for tool in ("cutwitness_c", "ablate_random_suffix"):          # v5: only suffix-executing arms; never suffix-free arms
            us = [u for u in search if u["target"] == t and u["tool"] == tool]
            if us:
                x, e = _times(us, "first_latent_candidate_at", budget); curves[tool] = kaplan_meier(x, e)
        if curves:
            w(f"fig_latent_survival_{t}.svg", svgplot.steps(f"Descriptive matched-arm survival curves ({t}): CutWitness-C vs matched random suffix", curves, budget, label))
    # blind adjudication worksheet (no method identity) and the separately revealed method map
    ws = [{"witness_id": wi["id"], "target": wi["target"], "workload": wi.get("workload"), "operators": ";".join(wi.get("operators", [])),
           "triage_class": wi["class"], "primary_class_suggested": primary_class(wi), "latent": wi.get("latent"),
           "lifecycle_kinds": ";".join(wi.get("lifecycle_kinds", [])), "minimized_length": wi.get("minimized_len"),
           "terminal_digest": wi.get("terminal_digest"), "witness_status": wi["status"],
           "latent_attribution": (wi.get("attribution") or {}).get("attribution_class", "NOT_LATENT" if not wi.get("latent") else "NOT_ATTRIBUTED")} for wi in witnesses]
    w("adjudication_worksheet.csv", _rows_csv(ws, ["witness_id", "target", "workload", "operators", "triage_class", "primary_class_suggested",
                                                   "latent", "lifecycle_kinds", "minimized_length", "terminal_digest", "witness_status", "latent_attribution"]))
    att = [dict(wi["attribution"]) for wi in sorted(witnesses, key=lambda z: z["id"]) if wi.get("attribution")]
    w("latent_attribution.csv", _rows_csv(att, ["witness_id", "target", "workload", "final_cut_digest", "continuation_digest",
                                                "history_path_result", "fresh_cut_result", "canonical_path_result", "canonical_transactions",
                                                "canonical_independent_of_history", "attribution_class", "attribution_detail",
                                                "reason", "replays_per_path"]))
    w("witness_method_map.csv", _rows_csv([{"witness_id": wi["id"], "method": wi.get("tool")} for wi in witnesses], ["witness_id", "method"]))



# ---------------------------------------------------------------- RQ2b matched pairs (ANALYSIS_SPEC_v6, Amendment v1.5)
class RQ2bBlocked(Exception):
    pass


PAIR_TREATMENT, PAIR_CONTROL = "cutwitness_c", "ablate_random_suffix"
DELMATCH_CONTROL = "ablate_deletion_matched_suffix"          # V1.8: separate family RQ2c (Holm across targets)


def rq2b_pairs(units, cfg, budget, control=None):
    control = control or PAIR_CONTROL
    """Exactly one treatment and one control unit per target x workload x rep in the control's mapped cells; fail closed."""
    cells = cfg["matrix"]["ablation_map"].get(control)
    if not cells:
        return []
    full = [u for u in units if u.get("phase", "full") == "full"]
    reps = range(cfg["full"]["trials"])
    pairs = []
    for t in cells["targets"]:
        for wl in cells["workloads"]:
            for rep in reps:
                a = [u for u in full if u["tool"] == PAIR_TREATMENT and u["target"] == t and u["workload"] == wl and u["trial"] == rep]
                b = [u for u in full if u["tool"] == control and u["target"] == t and u["workload"] == wl and u["trial"] == rep]
                if len(a) != 1 or len(b) != 1:
                    raise RQ2bBlocked(f"{t}/{wl}/rep{rep}: {len(a)} {PAIR_TREATMENT} and {len(b)} {control} units (need exactly 1 each)")
                a, b = a[0], b[0]
                checks = {"seed": a.get("seed") == b.get("seed"), "budget": a.get("budget_kind") == b.get("budget_kind"),
                          "applicability": latent_endpoint_applicable(a["tool"]) and latent_endpoint_applicable(b["tool"]),
                          "workload": a["workload"] == b["workload"], "target": a["target"] == b["target"], "rep": a["trial"] == b["trial"]}
                bad = [k for k, ok in checks.items() if not ok]
                if bad:
                    raise RQ2bBlocked(f"{t}/{wl}/rep{rep}: pair mismatch on {bad}")
                pairs.append((a, b))
    return pairs


def pair_outcome(t_cw, e_cw, t_rs, e_rs) -> str:
    if e_cw and (not e_rs or t_cw < t_rs):
        return "CW_WIN"
    if e_rs and (not e_cw or t_rs < t_cw):
        return "RANDOM_WIN"
    return "TIE"            # both censored, or observed at exactly the same recorded search time


def rq2b_outputs(units, cfg, label, budget, w, control=None, prefix="rq2b") -> str:
    control = control or PAIR_CONTROL
    hk = f"holm_p_within_{prefix}"; ck = "random_suffix_unit_id" if prefix == "rq2b" else "deletion_matched_unit_id"
    from .stats import clopper_pearson, sign_test_two_sided
    pcols = ["target", "workload", "rep", "cw_unit_id", ck, "cw_event", "random_event", "cw_time", "random_time", "pair_outcome"]
    scols = ["target", "pairs_total", "cw_wins", "random_wins", "ties", "informative_pairs", "cw_win_fraction", "ci_low", "ci_high",
             "exact_sign_p", hk, "holm_family_size", "status"]
    try:
        pairs = rq2b_pairs(units, cfg, budget, control)
    except RQ2bBlocked as e:
        msg = f"RQ2B_ANALYSIS_BLOCKED: {e}"
        w(f"{prefix}_matched_pairs.csv", _rows_csv([], pcols))
        w(f"{prefix}_matched_summary.csv", _rows_csv([{"target": "ALL", "status": msg}], scols))
        return msg
    prow = []
    for a, b in pairs:
        ta = a["first_latent_candidate_at"] if a.get("first_latent_candidate_at") is not None else budget
        tb = b["first_latent_candidate_at"] if b.get("first_latent_candidate_at") is not None else budget
        ea, eb = int(a.get("first_latent_candidate_at") is not None), int(b.get("first_latent_candidate_at") is not None)
        prow.append({"target": a["target"], "workload": a["workload"], "rep": a["trial"], "cw_unit_id": a["unit_id"], ck: b["unit_id"],
                     "cw_event": ea, "random_event": eb, "cw_time": ta, "random_time": tb, "pair_outcome": pair_outcome(ta, ea, tb, eb)})
    w(f"{prefix}_matched_pairs.csv", _rows_csv(prow, pcols))
    srows = []
    for t in sorted({r["target"] for r in prow}):
        rs = [r for r in prow if r["target"] == t]
        W = sum(r["pair_outcome"] == "CW_WIN" for r in rs); L = sum(r["pair_outcome"] == "RANDOM_WIN" for r in rs); N = W + L
        lo, hi = clopper_pearson(W, N)
        p = sign_test_two_sided(W, N)
        srows.append({"target": t, "pairs_total": len(rs), "cw_wins": W, "random_wins": L, "ties": len(rs) - N, "informative_pairs": N,
                      "cw_win_fraction": (W / N) if N else "N/A", "ci_low": lo if N else "N/A", "ci_high": hi if N else "N/A",
                      "exact_sign_p": p if p is not None else "N/A",
                      "status": "OK" if N else "NO_INFORMATIVE_DISCORDANT_PAIRS"})
    valid = [r for r in srows if r["exact_sign_p"] != "N/A"]
    for r, a in zip(valid, holm([r["exact_sign_p"] for r in valid]) if valid else []):
        r[hk] = a
    for r in srows:
        r.setdefault(hk, "N/A"); r["holm_family_size"] = len(valid)
    w(f"{prefix}_matched_summary.csv", _rows_csv(srows, scols))
    timing = []
    for t in sorted({r["target"] for r in prow}):
        rs = [r for r in prow if r["target"] == t]
        oc = [r["cw_time"] for r in rs if r["cw_event"]]; orr = [r["random_time"] for r in rs if r["random_event"]]
        both = [r["cw_time"] - r["random_time"] for r in rs if r["cw_event"] and r["random_event"]]
        timing.append({"target": t, "median_cw_time_observed": median(oc) if oc else "N/A", "median_random_time_observed": median(orr) if orr else "N/A",
                       "median_paired_difference_cw_minus_random_both_observed": median(both) if both else "N/A", "pairs_both_observed": len(both),
                       "note": "descriptive only; no test"})
    w(f"{prefix}_matched_timing.csv", _rows_csv(timing, ["target", "median_cw_time_observed", "median_random_time_observed",
                                                     "median_paired_difference_cw_minus_random_both_observed", "pairs_both_observed", "note"]))
    return f"OK ({len(prow)} pairs; Holm family size {len(valid)})"


# ---------------------------------------------------------------- equivalence-sampling instrumentation amendment v1
def rho_outputs(units, label, w):
    obs, summ = [], {}
    for u in units:
        rs = u.get("rho_sampling")
        if not rs:
            continue
        t = u["target"]
        s = summ.setdefault(t, {"label": label, "target": t, "units": 0, "equivalence_classes_formed": 0, "members_pruned": 0,
                                "sampled_members_selected": 0, "sampled_members_executed": 0, "comparable_pairs": 0, "matches": 0,
                                "divergences": 0, "errors": 0, "nondeterministic": 0, "representative_unavailable": 0, "distinct_divergent_members": 0})
        s["units"] += 1; s["equivalence_classes_formed"] += rs["classes_formed"]; s["members_pruned"] += rs["members_pruned"]
        s["sampled_members_selected"] += rs["sampled_selected"]; s["sampled_members_executed"] += rs["sampled_executed"]
        for r in rs["observations"]:
            st = r["comparison_status"]
            s["matches"] += st == "MATCH"; s["divergences"] += st == "DIVERGENCE"; s["errors"] += st == "SAMPLE_ERROR"
            s["nondeterministic"] += st == "NONDETERMINISTIC"; s["representative_unavailable"] += st == "REPRESENTATIVE_UNAVAILABLE"
            obs.append({"label": label, "unit_id": u["unit_id"], "target": t, "workload": u.get("workload"), "representative_unit_id": u["unit_id"], **r})
        s["comparable_pairs"] = s["matches"] + s["divergences"]
        s["distinct_divergent_members"] = len({o["member_history_id"] for o in obs if o["target"] == t and o["comparison_status"] == "DIVERGENCE"})
    cols = ["label", "unit_id", "target", "workload", "equivalence_class_id", "representative_history_id", "representative_unit_id", "member_history_id",
            "is_representative", "selected_as_rho_sample", "rho_sampling_seed", "operator_key_fingerprint", "executed", "representative_output_digest",
            "sampled_member_output_digest", "equal", "comparison_status"]
    scols = ["label", "target", "units", "equivalence_classes_formed", "members_pruned", "sampled_members_selected", "sampled_members_executed",
             "comparable_pairs", "matches", "divergences", "errors", "nondeterministic", "representative_unavailable", "distinct_divergent_members"]
    w("rho_sampling_observations.csv", _rows_csv(obs, cols))
    w("rho_sampling_summary.csv", _rows_csv(sorted(summ.values(), key=lambda z: z["target"]), scols))
