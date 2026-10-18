"""Amendment v1.3: suffix-free arms cannot emit latent witnesses; RQ2 emits no inferential no-suffix latent statistics."""
import csv, os, random, subprocess, sys
import pytest
from cutwitness.pipeline import TOOLS, run_trial
from cutwitness.toyengine import ToyEngine
from cutwitness.w3 import gen_history, gen_schema, gen_views

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUFFIX_FREE = sorted(t for t, c in TOOLS.items() if not c.get("suffix"))


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("tool", SUFFIX_FREE)
def test_no_suffix_cannot_emit_latent_witness(tool, seed):
    rng = random.Random(seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6)
    r = run_trial(tool, lambda: ToyEngine(s, vs, "F9_LATENT_RESIDUAL"), ToyEngine.caps, s, vs, h, 6, 2, 0.1, 99 + seed,
                  minimize_witnesses=False)
    assert r["first_latent_candidate_at"] is None and r["latent_censored"] is True
    assert all(d["latent"] is False for d in r["divergences"])
    assert "ablate_no_suffix" in SUFFIX_FREE


def test_rq2_analysis_emits_no_inferential_no_suffix_latent_statistics(tmp_path):
    d = str(tmp_path / "run")
    assert subprocess.run([sys.executable, "-m", "cutwitness.one_shot", "--config", os.path.join(ROOT, "campaign", "CRASHTEST_SIMULATION.yaml"),
                           "--run-dir", d], cwd=ROOT, capture_output=True).returncode == 0
    a = os.path.join(d, "analysis", "SYNTHETIC_ENGINEERING")
    comps = list(csv.DictReader(open(os.path.join(a, "rq_ablation_comparisons.csv"))))
    assert all(r["family"] != "ablate_no_suffix" for r in comps)
    for f in os.listdir(a):
        if f.startswith("fig_latent_survival"):
            assert "ablate_no_suffix" not in open(os.path.join(a, f)).read()
    rq2 = {r["tool"]: r["latent_candidates"] for r in csv.DictReader(open(os.path.join(a, "rq2_latent.csv")))}
    for t in rq2:
        if t in SUFFIX_FREE:
            assert rq2[t].startswith("N/A"), (t, rq2[t])
    lt = list(csv.DictReader(open(os.path.join(a, "latent_ttf_event.csv"))))
    assert all((r["latent_endpoint"] == "NOT_APPLICABLE_BY_DESIGN") == (r["method"] in SUFFIX_FREE) for r in lt)


def test_registry_never_classes_the_adjudication_ledger_as_automatic():
    from cutwitness.adjudication import validate_registry
    bad = [{"manuscript_location": "x", "metric_name": "m", "analysis_artifact": "root_cause_adjudication_ledger.csv",
            "raw_artifact": "", "producer_status": "EXISTS"}]
    assert validate_registry(bad)
    rows = list(csv.DictReader(open(os.path.join(ROOT, "MANUSCRIPT_EVIDENCE_REGISTRY.csv"))))
    assert validate_registry(rows) == []
