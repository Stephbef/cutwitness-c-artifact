"""Frozen statistics and analysis outputs."""
import json, os, random, xml.dom.minidom
import pytest
from cutwitness.analysis import analyze
from cutwitness.stats import a12, bootstrap_ci, holm, kaplan_meier, logrank, mann_whitney, ratio_of_medians

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "mannwhitney_reference.json")


def test_mann_whitney_matches_frozen_scipy_reference_fixture():
    cases = json.load(open(FX))["cases"]
    assert len(cases) == 120 and any(len(set(c["x"] + c["y"])) < len(c["x"] + c["y"]) for c in cases)   # ties present
    for c in cases:
        assert mann_whitney(c["x"], c["y"]) == pytest.approx(c["p"], abs=1e-12)


def test_a12_ratio_holm_known_values():
    assert a12([3, 4], [1, 2]) == 1.0 and a12([1, 2], [3, 4]) == 0.0 and a12([1, 1], [1, 1]) == 0.5
    assert ratio_of_medians([2, 4, 6], [1, 2, 3]) == 2.0
    assert holm([0.01, 0.02, 0.03]) == pytest.approx([0.03, 0.04, 0.04]) and holm([0.5]) == [0.5]


def test_bootstrap_is_seed_deterministic():
    x = [3, 1, 4, 1, 5, 9, 2, 6]
    assert bootstrap_ci(x, n=10000, seed=0) == bootstrap_ci(x, n=10000, seed=0)


def test_kaplan_meier_right_censoring_and_zero_bug_runs():
    assert kaplan_meier([10, 20, 30, 40], [1, 0, 1, 0]) == [(0.0, 1.0), (10, 0.75), (30, 0.375)]
    assert kaplan_meier([100, 100, 100], [0, 0, 0]) == [(0.0, 1.0)]                 # all zero-bug: no drop
    assert logrank([100, 100], [0, 0], [100, 100], [0, 0]) == 1.0


def test_logrank_hand_computed_example():
    # Group 1 events at t=1,2; group 2 events at t=3,4 (all observed). Hand computation: O1-E1 = 2 - 0.8333..., Var = 0.7917...
    p = logrank([1, 2], [1, 1], [3, 4], [1, 1])
    import math
    o_e = (1 - 2 / 4) + (1 - 1 / 3)
    var = (1 * 0.5 * 0.5 * 3 / 3) + (1 * (1 / 3) * (2 / 3) * 2 / 2)
    assert p == pytest.approx(math.erfc(math.sqrt(o_e ** 2 / var / 2)))


def _unit(tool, tg, t, cands=0, latent=0):
    d = [{"triage": {"class": "TARGET_MAINTENANCE_BUG", "candidate": True}, "latent": i < latent} for i in range(cands)]
    return {"tool": tool, "target": tg, "first_candidate_at": t, "divergences": d, "coverage": {"GROUP": 5}, "unit_class": "SEARCH_TRIAL"}


def test_analysis_tables_and_svg_generation(tmp_path):
    cfg = {"statistics": {"bootstrap_resamples": 500, "bootstrap_seed": 0}, "matrix": {"search_tools": ["cutwitness_c", "baseline_random_clean"], "ablation_map": {}}, "analysis_spec": {"ablation_families": {}}}
    units = [_unit("cutwitness_c", "pg_ivm", 10 + i, 1, 1) for i in range(5)] + [_unit("baseline_random_clean", "pg_ivm", None) for i in range(5)]
    wits = [{"id": "w1", "target": "pg_ivm", "class": "TARGET_MAINTENANCE_BUG", "signature": "s", "status": "NEW",
             "original_len": 9, "minimized_len": 2, "ddmin_len": 3, "ddmin_calls": 20}]
    s1 = analyze(units, cfg, "SYNTHETIC_ENGINEERING_TEST", 100, str(tmp_path / "a"), wits)
    s2 = analyze(units, cfg, "SYNTHETIC_ENGINEERING_TEST", 100, str(tmp_path / "b"), wits)
    assert s1 == s2 and s1["candidates"] == 5
    for f in os.listdir(tmp_path / "a"):
        a, b = open(tmp_path / "a" / f, "rb").read(), open(tmp_path / "b" / f, "rb").read()
        assert a == b, f
        if f.endswith(".svg"):
            xml.dom.minidom.parseString(a)
            assert b"SYNTHETIC_ENGINEERING_TEST" in a
    rows = open(tmp_path / "a" / "rq3_comparisons.csv").read().splitlines()
    assert len(rows) == 2 and "baseline_random_clean" in rows[1]



def test_analysis_holm_is_scoped_per_target_five_baseline_family(tmp_path):
    """Regression: frozen multiplicity is 3 independent target families, never one global-15 family."""
    from cutwitness.stats import holm
    import csv

    targets = ["pg_ivm", "feldera", "risingwave"]
    baselines = [
        "baseline_random_clean",
        "baseline_random_te",
        "baseline_stateful_fuzz",
        "baseline_zippy",
        "baseline_source_por",
    ]
    cfg = {
        "statistics": {"bootstrap_resamples": 100, "bootstrap_seed": 0},
        "matrix": {"search_tools": ["cutwitness_c"] + baselines, "ablation_map": {}},
        "analysis_spec": {"ablation_families": {}},
    }
    units = []
    # Deliberately make target effect sizes differ so global-15 Holm and per-target-5 Holm diverge.
    cw_times = {
        "pg_ivm": [1, 2, 3, 4, 5, 6, 7, 8],
        "feldera": [8, 9, 10, 11, 12, 13, 14, 15],
        "risingwave": [2, 3, 4, 5, 6, 7, 8, 9],
    }
    offsets = {
        "pg_ivm": [12, 10, 8, 6, 4],
        "feldera": [7, 5, 3, 1, 0],
        "risingwave": [14, 11, 9, 7, 5],
    }
    for t in targets:
        units += [_unit("cutwitness_c", t, x) for x in cw_times[t]]
        for tool, off in zip(baselines, offsets[t]):
            units += [_unit(tool, t, x + off) for x in cw_times[t]]

    analyze(units, cfg, "SYNTHETIC_ENGINEERING_TEST", 100, str(tmp_path / "holm"), [])
    with open(tmp_path / "holm" / "rq3_comparisons.csv", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 15
    raw_global = [float(r["mann_whitney_p"]) for r in rows]
    global_adj = holm(raw_global)
    emitted = [float(r["holm_p"]) for r in rows]
    assert any(abs(a - b) > 1e-15 for a, b in zip(emitted, global_adj)), "fixture must distinguish global vs per-target Holm"

    for t in targets:
        group = [r for r in rows if r["target"] == t]
        assert len(group) == 5
        expected = holm([float(r["mann_whitney_p"]) for r in group])
        assert [float(r["holm_p"]) for r in group] == pytest.approx(expected, abs=1e-15)

def test_exact_seed_replay_of_a_trial():
    from cutwitness.model import sha
    from cutwitness.pipeline import run_trial
    from cutwitness.toyengine import ToyEngine
    from cutwitness.w3 import gen_history, gen_schema, gen_views
    rng = random.Random(4); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6)
    r = [run_trial("cutwitness_c", lambda: ToyEngine(s, vs, "F9_LATENT_RESIDUAL"), ToyEngine.caps, s, vs, h, 4, 2, 0.1, 77,
                   minimize_witnesses=False) for _ in range(2)]
    assert sha(r[0]) == sha(r[1])


def test_witness_deduplication_by_target_history_class(tmp_path):
    from cutwitness import controller
    from cutwitness.config import load
    from decimal import Decimal as D
    from cutwitness.model import Schema, Table, Txn, ZSet
    from cutwitness.refmodel import GroupAgg, Scan, View
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = load(os.path.join(root, "campaign", "CRASHTEST_SIMULATION.yaml"))
    s = Schema([Table("t0", [("id", "int", False), ("k", "int", False), ("v", "dec", True)], pk=[0])])
    v = View("v", GroupAgg("g", Scan("s", "t0", 3), [1], [("COUNT", None)]))
    h = [Txn({"t0": ZSet([((1, 3, D("1")), 1)])}).canon()]
    d = {"triage": {"candidate": True, "class": "TARGET_MAINTENANCE_BUG"}, "history_digest": "same", "history": h, "suffix": [], "obs_digest": "x", "where": "cut"}
    units = [{"unit_id": f"u{i}", "target": "pg_ivm", "workload": "W3", "tool": "cutwitness_c", "schema": s.to_json(), "views": [v.to_json()], "divergences": [d, d]} for i in range(3)]
    assert len(controller.witness_closure(cfg, str(tmp_path), units)) == 1
