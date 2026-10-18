"""Equivalence-sampling instrumentation amendment v1: logging only; the same histories execute in the same order."""
import csv, json, os, random, subprocess, sys
import pytest
from cutwitness import pipeline as PL
from cutwitness.toyengine import ToyEngine
from cutwitness.w3 import gen_history, gen_schema, gen_views

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(seed, fault, flag, monkeypatch, tool="cutwitness_c"):
    monkeypatch.setattr(PL, "RHO_INSTRUMENTATION", flag)
    rng = random.Random(seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6)
    return PL.run_trial(tool, lambda: ToyEngine(s, vs, fault), ToyEngine.caps, s, vs, h, 30, 2, 0.5, 31 + seed, minimize_witnesses=False)


@pytest.mark.parametrize("seed", range(3))
@pytest.mark.parametrize("fault", ["NONE", "F10_CROSS_KEY_OUT_OF_MODEL", "F9_LATENT_RESIDUAL"])
def test_instrumentation_is_non_selection(seed, fault, monkeypatch):
    a = _run(seed, fault, False, monkeypatch); b = _run(seed, fault, True, monkeypatch)
    strip = lambda r: json.dumps({k: v for k, v in r.items() if k != "rho_sampling"}, sort_keys=True, default=str)
    assert strip(a) == strip(b)
    assert a["rho_sampling"] is None and b["rho_sampling"] is not None


@pytest.mark.parametrize("seed", range(3))
def test_counts_and_statuses_are_consistent(seed, monkeypatch):
    rs = _run(seed, "F10_CROSS_KEY_OUT_OF_MODEL", True, monkeypatch)["rho_sampling"]
    obs = rs["observations"]
    assert rs["sampled_selected"] == len(obs) and rs["sampled_executed"] == sum(o["executed"] for o in obs) <= len(obs)
    assert all(o["comparison_status"] in PL.RHO_STATUSES for o in obs)
    assert all(o["comparison_status"] == "NOT_COMPARABLE" for o in obs if not o["executed"])
    assert all((o["equal"] is True) == (o["comparison_status"] == "MATCH") for o in obs if o["comparison_status"] in ("MATCH", "DIVERGENCE"))


def test_in_model_engine_shows_no_intra_class_divergence(monkeypatch):
    for seed in range(4):
        for o in _run(seed, "NONE", True, monkeypatch)["rho_sampling"]["observations"]:
            assert o["comparison_status"] != "DIVERGENCE"


def test_suffix_free_and_source_reduction_arms_record_nothing(monkeypatch):
    assert _run(1, "NONE", True, monkeypatch, tool="baseline_random_clean")["rho_sampling"] is None
    assert _run(1, "NONE", True, monkeypatch, tool="baseline_source_por")["rho_sampling"] is None


def test_campaign_emits_rho_csvs(tmp_path):
    d = str(tmp_path / "run")
    assert subprocess.run([sys.executable, "-m", "cutwitness.one_shot", "--config", os.path.join(ROOT, "campaign", "CRASHTEST_SIMULATION.yaml"),
                           "--run-dir", d], cwd=ROOT, capture_output=True).returncode == 0
    a = os.path.join(d, "analysis", "SYNTHETIC_ENGINEERING")
    summ = list(csv.DictReader(open(os.path.join(a, "rho_sampling_summary.csv"))))
    assert summ and all(int(r["comparable_pairs"]) == int(r["matches"]) + int(r["divergences"]) for r in summ)
    assert os.path.exists(os.path.join(a, "rho_sampling_observations.csv"))


def _rho_run(seed, fault="NONE", junk=0):
    rng = random.Random(5000 + seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 8)
    keep = [tuple(range(i % 7)) for i in range(junk)]          # perturb allocator free lists / object addresses
    r = PL.run_trial("cutwitness_c", lambda: ToyEngine(s, vs, fault), ToyEngine.caps, s, vs, h, 60, 2, 0.1, 6000 + seed, minimize_witnesses=False)
    del keep
    return r


@pytest.mark.parametrize("seed", (1, 2))
def test_rho_records_independent_of_object_addresses(seed):
    """V1.7.2: bookkeeping is keyed by history digest, never id(); allocation perturbation must not change the records."""
    a = _rho_run(seed)["rho_sampling"]; b = _rho_run(seed, junk=5000)["rho_sampling"]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.parametrize("seed", (0, 1, 2))
def test_executed_samples_name_executed_histories(seed):
    r = _rho_run(seed, "F10_CROSS_KEY_OUT_OF_MODEL")
    ex = {x["history_id"] for x in r["execution_log"] if x.get("executed") and x.get("category") == "search"}
    for o in r["rho_sampling"]["observations"]:
        assert (not o["executed"]) or o["member_history_id"] in ex
