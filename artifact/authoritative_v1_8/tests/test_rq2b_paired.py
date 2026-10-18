"""Amendment v1.5: RQ2b is a matched-pair analysis (exact sign test, Holm over targets); no unpaired statistics."""
import csv, io, os, subprocess, sys
import pytest
from cutwitness.analysis import PAIR_CONTROL, PAIR_TREATMENT, RQ2bBlocked, pair_outcome, rq2b_outputs, rq2b_pairs
from cutwitness.config import load
from cutwitness.matrix import build_matrix
from cutwitness.stats import clopper_pearson, holm, sign_test_two_sided

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))
B = CFG["full"]["budget"]["value"]


def units_from_matrix(times=None):
    us = []
    for r in build_matrix(CFG):
        if r["stage"] == "full" and r["tool"] in (PAIR_TREATMENT, PAIR_CONTROL):
            k = (r["tool"], r["target"], r["workload"], r["rep"])
            us.append({"unit_id": r["unit_id"], "phase": "full", "tool": r["tool"], "target": r["target"], "workload": r["workload"],
                       "trial": r["rep"], "seed": r["seed"], "budget_kind": "seconds", "first_latent_candidate_at": (times or {}).get(k)})
    return us


def run_outputs(units):
    files = {}
    status = rq2b_outputs(units, CFG, "TEST", B, lambda name, text: files.__setitem__(name, text))
    rd = lambda n: list(csv.DictReader(io.StringIO(files[n])))
    return status, rd


def test_thirty_matched_pairs_per_target_in_frozen_matrix():
    pairs = rq2b_pairs(units_from_matrix(), CFG, B)
    assert len(pairs) == 90
    for t in ("pg_ivm", "feldera", "risingwave"):
        assert sum(a["target"] == t for a, _ in pairs) == 30
    assert all(a["seed"] == b["seed"] for a, b in pairs)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "seed"])
def test_missing_duplicate_or_mismatched_pairs_fail_closed(damage):
    us = units_from_matrix()
    ctrl = [u for u in us if u["tool"] == PAIR_CONTROL]
    if damage == "missing":
        us.remove(ctrl[0])
    elif damage == "duplicate":
        us.append(dict(ctrl[0]))
    else:
        ctrl[0]["seed"] = ctrl[0]["seed"] + 1
    with pytest.raises(RQ2bBlocked):
        rq2b_pairs(us, CFG, B)
    status, rd = run_outputs(us)
    assert status.startswith("RQ2B_ANALYSIS_BLOCKED") and rd("rq2b_matched_pairs.csv") == []
    assert rd("rq2b_matched_summary.csv")[0]["status"].startswith("RQ2B_ANALYSIS_BLOCKED")


def test_pair_outcome_rules():
    assert pair_outcome(100, 1, B, 0) == "CW_WIN"            # CW event vs random censored
    assert pair_outcome(B, 0, 200, 1) == "RANDOM_WIN"        # random event vs CW censored
    assert pair_outcome(B, 0, B, 0) == "TIE"                 # both censored (common censoring)
    assert pair_outcome(100, 1, 200, 1) == "CW_WIN"          # earlier of two events wins
    assert pair_outcome(300, 1, 200, 1) == "RANDOM_WIN"
    assert pair_outcome(150, 1, 150, 1) == "TIE"             # equal recorded times


def test_exact_sign_test_and_clopper_pearson_fixtures():
    assert sign_test_two_sided(8, 10) == pytest.approx(112 / 1024)       # 2*(45+10+1)/1024
    assert sign_test_two_sided(10, 10) == pytest.approx(2 / 1024)
    assert sign_test_two_sided(5, 10) == pytest.approx(1.0)
    assert sign_test_two_sided(0, 5) == pytest.approx(2 / 32)
    assert sign_test_two_sided(0, 0) is None
    lo, hi = clopper_pearson(8, 10); assert lo == pytest.approx(0.44390, abs=1e-4) and hi == pytest.approx(0.97479, abs=1e-4)
    lo, hi = clopper_pearson(0, 10); assert lo == 0.0 and hi == pytest.approx(0.30850, abs=1e-4)
    assert clopper_pearson(0, 0) == (None, None)


def test_holm_across_targets_and_reduced_family():
    times = {}
    for r in build_matrix(CFG):
        if r["stage"] == "full" and r["tool"] in (PAIR_TREATMENT, PAIR_CONTROL):
            k = (r["tool"], r["target"], r["workload"], r["rep"])
            if r["target"] == "pg_ivm":                       # 30 CW wins
                times[k] = 100 if r["tool"] == PAIR_TREATMENT else None
            elif r["target"] == "feldera":                    # all ties (both censored) -> N = 0
                times[k] = None
            else:                                             # rep < 7: CW wins, else random wins
                times[k] = (100 if r["tool"] == PAIR_TREATMENT else 200) if r["rep"] < 7 else (300 if r["tool"] == PAIR_TREATMENT else 200)
    status, rd = run_outputs(units_from_matrix(times))
    s = {r["target"]: r for r in rd("rq2b_matched_summary.csv")}
    assert s["feldera"]["exact_sign_p"] == "N/A" and s["feldera"]["status"] == "NO_INFORMATIVE_DISCORDANT_PAIRS"
    assert s["pg_ivm"]["cw_wins"] == "30" and s["risingwave"]["cw_wins"] == "21" and s["risingwave"]["random_wins"] == "9"
    p_pg, p_rw = sign_test_two_sided(30, 30), sign_test_two_sided(21, 30)
    exp = dict(zip(["pg_ivm", "risingwave"], holm([p_pg, p_rw])))
    for t in exp:
        assert float(s[t]["holm_p_within_rq2b"]) == pytest.approx(exp[t]) and s[t]["holm_family_size"] == "2"
    assert "family size 2" in status


def test_rq2b_emits_no_unpaired_statistics(tmp_path):
    status, rd = run_outputs(units_from_matrix())
    cols = set(rd("rq2b_matched_summary.csv")[0]) | set(rd("rq2b_matched_pairs.csv")[0])
    for bad in ("mann", "a12", "logrank", "log_rank"):
        assert not any(bad in c.lower() for c in cols)
    d = str(tmp_path / "run")
    assert subprocess.run([sys.executable, "-m", "cutwitness.one_shot", "--config", os.path.join(ROOT, "campaign", "CRASHTEST_SIMULATION.yaml"),
                           "--run-dir", d], cwd=ROOT, capture_output=True).returncode == 0
    a = os.path.join(d, "analysis", "SYNTHETIC_ENGINEERING")
    comps = list(csv.DictReader(open(os.path.join(a, "rq_ablation_comparisons.csv"))))
    assert all(r["family"] != PAIR_CONTROL for r in comps)                  # no MW / A12 / log-rank row for RQ2b
    summ = list(csv.DictReader(open(os.path.join(a, "rq2b_matched_summary.csv"))))
    assert summ and all(r["status"] in ("OK", "NO_INFORMATIVE_DISCORDANT_PAIRS") for r in summ)
    for f in os.listdir(a):
        if f.startswith("fig_latent_survival"):
            assert "Descriptive matched-arm survival curves" in open(os.path.join(a, f)).read()
