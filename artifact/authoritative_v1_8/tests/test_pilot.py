"""Every decision path of the frozen pilot gate (signals A-D), thresholds exactly as frozen."""
from cutwitness.pilot import evaluate

SIG = {"A": 1, "B_speedup": 2.0, "B_a12": 0.71, "D_coverage_ratio": 3.0}
BASE = ["baseline_random_clean", "baseline_random_te", "baseline_zippy"]
TG = ["pg_ivm", "risingwave"]


def cand(cls="TARGET_MAINTENANCE_BUG", latent=False):
    return {"triage": {"class": cls, "candidate": True}, "latent": latent}


def unit(tool, tg, t=None, divs=(), cov=10):
    return {"tool": tool, "target": tg, "first_candidate_at": t, "divergences": list(divs), "coverage": {"GROUP": cov}}


def bundle(cw_t=None, cw_div=(), cw_cov=10, b_t=None, b_div=(), b_cov=10, trials=3):
    us = []
    for tg in TG:
        for i in range(trials):
            us.append(unit("cutwitness_c", tg, cw_t, cw_div, cw_cov))
            for b in BASE:
                us.append(unit(b, tg, b_t, b_div, b_cov))
    return us


def ev(us, planned=None, budget=100):
    return evaluate(us, len(us) if planned is None else planned, SIG, budget, BASE, TG)


def test_only_A():
    r = ev(bundle(cw_t=90, cw_div=[cand()], b_t=95, b_div=[cand()]))
    assert r["signals"]["A"] and not r["signals"]["B"] and not r["signals"]["C"] and not r["signals"]["D"] and r["decision"] == "GO"


def test_only_B_impossible_without_candidates_then_B_with_A():
    r = ev(bundle(cw_t=10, cw_div=[cand()], b_t=100))
    assert r["signals"]["B"] and r["signals"]["A"]


def test_only_C():
    sig = dict(SIG, A=10**6)                         # make A unattainable to isolate C
    us = bundle(cw_t=50, cw_div=[cand(latent=True)], b_t=60, b_div=[cand()])
    r = evaluate(us, len(us), sig, 100, BASE, TG)
    assert r["signals"]["C"] and not r["signals"]["A"] and not r["signals"]["B"] and not r["signals"]["D"]


def test_only_D():
    sig = dict(SIG, A=10**6)
    r = evaluate(bundle(cw_cov=30, b_cov=10), 24, sig, 100, BASE, TG)
    assert r["signals"]["D"] and not any(r["signals"][k] for k in "ABC") and r["decision"] == "GO"


def test_multiple_signals():
    r = ev(bundle(cw_t=10, cw_div=[cand(latent=True)], cw_cov=40, b_t=100, b_cov=10))
    assert all(r["signals"][k] for k in "ABCD")


def test_no_signal_is_no_go():
    r = ev(bundle())
    assert r["decision"] == "PILOT_NO_GO" and not any(r["signals"][k] for k in "ABCD")


def test_threshold_edges_B_and_D():
    sig = dict(SIG, A=10**6)
    exact2 = evaluate(bundle(cw_t=50, cw_div=[cand()], b_t=100, b_div=[cand()]), 24, sig, 100, BASE, TG)
    assert exact2["signals"]["B"]                    # exactly 2x faster and A12 = 1.0 passes (>= thresholds)
    under = evaluate(bundle(cw_t=51, cw_div=[cand()], b_t=100, b_div=[cand()]), 24, sig, 100, BASE, TG)
    assert not under["signals"]["B"]
    assert evaluate(bundle(cw_cov=30, b_cov=10), 24, sig, 100, BASE, TG)["signals"]["D"]       # exactly 3x
    assert not evaluate(bundle(cw_cov=29, b_cov=10), 24, sig, 100, BASE, TG)["signals"]["D"]


def test_missing_unit_is_incomplete():
    us = bundle(cw_t=10, cw_div=[cand()])
    r = ev(us[:-1], planned=len(us))
    assert r["decision"] == "INCOMPLETE"


def test_zero_divergence_and_right_censoring():
    r = ev(bundle(cw_t=None, b_t=None))
    assert not r["signals"]["A"] and not r["signals"]["B"] and r["decision"] == "PILOT_NO_GO"


def test_unresolved_and_non_candidate_divergences_do_not_count():
    unres = {"triage": {"class": "UNRESOLVED", "candidate": False}, "latent": True}
    nondet = {"triage": {"class": "TARGET_NONDETERMINISM", "candidate": False}, "latent": False}
    r = ev(bundle(cw_div=[unres, nondet]))
    assert not r["signals"]["A"] and not r["signals"]["C"]


def test_not_applicable_baseline_rows_are_ignored_not_passed():
    us = bundle(cw_t=10, cw_div=[cand()], b_t=100)
    us.append({"tool": "baseline_native_suite", "target": "risingwave", "unit_class": "NOT_APPLICABLE", "divergences": [],
               "first_candidate_at": None, "coverage": {}})
    r = evaluate(us, len(us), SIG, 100, BASE, TG)
    assert r["decision"] == "GO" and "baseline_native_suite" not in BASE


def test_insufficient_data_for_B_on_one_target():
    us = [u for u in bundle(cw_t=10, cw_div=[cand()], b_t=100) if not (u["target"] == "risingwave" and u["tool"] != "cutwitness_c")]
    r = evaluate(us, len(us), SIG, 100, BASE, TG)
    assert r["signals"]["B_per_target"]["risingwave"] is False and not r["signals"]["B"]
