"""Amendment v1.4: the matched random-suffix arm differs from CutWitness-C only in the suffix-construction rule."""
import csv, inspect, os, random, subprocess, sys
import pytest
from cutwitness import pipeline as PL
from cutwitness import suffix as SX
from cutwitness.analysis import latent_endpoint_applicable
from cutwitness.config import load
from cutwitness.matrix import build_matrix, summarize
from cutwitness.model import apply_txn, legal_state, src
from cutwitness.preflight import duration_preflight
from cutwitness.refmodel import Join, linear_source
from cutwitness.stats import holm
from cutwitness.toyengine import ToyEngine
from cutwitness.w3 import gen_history, gen_schema, gen_views

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = 2 ** 30


def cases(n=40):
    out = []
    for seed in range(n):
        rng = random.Random(seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6); x = src(s, h)
        for v in vs:
            if v.exposed():
                keys = sorted(v.top.key_rows(x, {}).keys(), key=repr)
                if keys:
                    out.append((s, v, x, keys[0], seed))
    return out


def _random(s, v, x, key, seed):
    L = SX.opportunity_length(s, v, x, key)
    return SX.random_suffix(s, v, x, key, L, random.Random(seed)), L


def test_requested_length_equals_characterization_length_and_same_support():
    checked = 0
    for s, v, x, key, seed in cases():
        try:
            ref, _ = SX.synthesize(s, v, x, key)
        except SX.SuffixUnsupported as e:
            if "illegal" in str(e):
                continue
            with pytest.raises(SX.SuffixUnsupported):
                SX.opportunity_length(s, v, x, key)
            continue
        assert SX.opportunity_length(s, v, x, key) == len(ref); checked += 1
    assert checked >= 30


def test_random_suffix_same_key_same_length_legal_every_prefix():
    n = 0
    for s, v, x, key, seed in cases():
        try:
            steps, L = _random(s, v, x, key, seed)
        except SX.SuffixUnsupported:
            continue
        assert len(steps) == L; n += 1
        op = v.top; cur = x
        sides = ("L", "R") if isinstance(op, Join) else (None,)
        srcs = {linear_source(SX.child_for(op, sd))[0]: sd for sd in sides}
        for t in steps:
            for table, z in t.delta.items():
                if table in srcs and len(set(srcs)) == len(sides):
                    sd = srcs[table]; f = linear_source(SX.child_for(op, sd))[1]
                    for r, m in z.items_sorted():
                        if m > 0:
                            y = f(r); assert y is not None and SX.op_key(op, y, sd) == key
            cur = apply_txn(cur, t); assert legal_state(s, cur)[0]
    assert n >= 30


def test_random_arm_never_calls_the_characterization_synthesizer(monkeypatch):
    for fn in (SX.random_suffix, SX.opportunity_length, SX._random_same_key_insert):
        assert "synthesize(" not in inspect.getsource(fn)
    rng = random.Random(3); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6)
    monkeypatch.setattr(PL, "synthesize", lambda *a, **k: (_ for _ in ()).throw(AssertionError("synthesizer called")))
    PL.run_trial("ablate_random_suffix", lambda: ToyEngine(s, vs, "F9_LATENT_RESIDUAL"), ToyEngine.caps, s, vs, h, 5, 2, 0.1, 7,
                 minimize_witnesses=False)
    with pytest.raises(AssertionError):
        PL.run_trial("cutwitness_c", lambda: ToyEngine(s, vs, "F9_LATENT_RESIDUAL"), ToyEngine.caps, s, vs, h, 5, 2, 0.1, 7,
                     minimize_witnesses=False)


@pytest.mark.parametrize("seed", range(5))
def test_matched_arms_execute_identical_histories(seed):
    rng = random.Random(seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6)
    run = lambda tool: PL.run_trial(tool, lambda: ToyEngine(s, vs, "NONE"), ToyEngine.caps, s, vs, h, 8, 2, 0.1, 4242 + seed,
                                    minimize_witnesses=False)
    a, b = run("cutwitness_c"), run("ablate_random_suffix")
    sa = [(r["history_id"], r["history_length"], r["suffix_length"]) for r in a["execution_log"] if r["executed"] and r["category"] == "search"]
    sb = [(r["history_id"], r["history_length"], r["suffix_length"]) for r in b["execution_log"] if r["executed"] and r["category"] == "search"]
    assert sa == sb and sa                                    # same candidates, same opportunity, same suffix lengths
    assert {k: v for k, v in PL.TOOLS["cutwitness_c"].items() if k != "suffix"} == \
           {k: v for k, v in PL.TOOLS["ablate_random_suffix"].items() if k != "suffix"}


def test_suffix_rng_is_deterministic_and_independent_of_search_rng():
    rng = random.Random(9); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6)
    run = lambda: PL.run_trial("ablate_random_suffix", lambda: ToyEngine(s, vs, "F9_LATENT_RESIDUAL"), ToyEngine.caps, s, vs, h, 6, 2,
                               0.1, 99, minimize_witnesses=False)
    a, b = run(), run()
    assert [r.get("suffix_id") for r in a["execution_log"]] == [r.get("suffix_id") for r in b["execution_log"]]
    assert PL._suffix_seed(99, 3) == PL._suffix_seed(99, 3) != PL._suffix_seed(99, 4)


def test_latent_endpoint_applies_to_random_suffix_and_not_to_no_suffix():
    assert latent_endpoint_applicable("ablate_random_suffix") and latent_endpoint_applicable("cutwitness_c")
    assert not latent_endpoint_applicable("ablate_no_suffix")
    found = False
    for seed in range(12):
        rng = random.Random(seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6)
        r = PL.run_trial("ablate_random_suffix", lambda: ToyEngine(s, vs, "F9_LATENT_RESIDUAL"), ToyEngine.caps, s, vs, h, 8, 2, 0.1,
                         500 + seed, minimize_witnesses=False)
        if r["first_latent_candidate_at"] is not None:
            found = True; break
    assert found, "the random-suffix arm must be able to produce latent events"


def test_matrix_arithmetic_and_matched_seeds():
    c = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml")); rows = build_matrix(c)
    rs = [r for r in rows if r["tool"] == "ablate_random_suffix"]
    assert len(rs) == 90 and all(r["unit_class"] == "ABLATION" and r["budget_value"] == 14400 for r in rs)
    cw = {(r["target"], r["workload"], r["rep"]): r["seed"] for r in rows if r["tool"] == "cutwitness_c" and r["stage"] == "full"}
    assert all(r["seed"] == cw[(r["target"], r["workload"], r["rep"])] for r in rs)
    s = summarize(rows, c["duration_gate"]["overhead_hours"])
    assert s["TOTAL_UNITS"] == 963 and s["ABLATION_UNITS"] == 360          # V1.8: + 90 deletion-matched units
    assert s["TOTAL_SEARCH_SLOT_HOURS"] + s["TOTAL_NONSEARCH_ESTIMATED_SLOT_HOURS"] == 4200
    assert all(r["tool"] != "ablate_random_suffix" for r in rows if r["stage"] == "pilot")


def test_45_day_gate_fails_closed():
    c = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))
    ok = duration_preflight(c, {"AVAILABLE_VCPUS": 64, "AVAILABLE_RAM_BYTES": 256 * G, "AVAILABLE_DISK_BYTES": 2048 * G})
    bad = duration_preflight(c, {"AVAILABLE_VCPUS": 26, "AVAILABLE_RAM_BYTES": 256 * G, "AVAILABLE_DISK_BYTES": 2048 * G})
    assert ok["CAMPAIGN_DURATION_PREFLIGHT"] == "PASS" and ok["PROJECTED_WALL_DAYS"] == 43.75   # V1.8: 4,200 slot-h / 4 slots
    assert bad["CAMPAIGN_DURATION_PREFLIGHT"] == "BLOCKED"


def test_inferential_families_are_disjoint_and_corrected_separately(tmp_path):
    c = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))
    fam = c["analysis_spec"]["ablation_families"]
    assert fam["ablate_random_suffix"] == {"rq": "RQ2b", "primary_metric": "matched_pair_exact_sign_test", "inferential": True, "paired": True}
    assert fam["ablate_no_suffix"]["inferential"] is False
    d = str(tmp_path / "run")
    assert subprocess.run([sys.executable, "-m", "cutwitness.one_shot", "--config", os.path.join(ROOT, "campaign", "CRASHTEST_SIMULATION.yaml"),
                           "--run-dir", d], cwd=ROOT, capture_output=True).returncode == 0
    a = os.path.join(d, "analysis", "SYNTHETIC_ENGINEERING")
    comps = list(csv.DictReader(open(os.path.join(a, "rq_ablation_comparisons.csv"))))
    assert {r["family"] for r in comps} <= set(fam) and "ablate_no_suffix" not in {r["family"] for r in comps}
    assert all(r["family"] != "ablate_random_suffix" for r in comps)          # v6: RQ2b is owned by the paired sign test
    assert os.path.exists(os.path.join(a, "rq2b_matched_summary.csv"))
    for f in {r["family"] for r in comps}:
        grp = [r for r in comps if r["family"] == f]
        assert [round(float(x), 12) for x in holm([float(r["mann_whitney_p"]) for r in grp])] == [round(float(r["holm_p_within_family"]), 12) for r in grp]
    base = list(csv.DictReader(open(os.path.join(a, "rq3_comparisons.csv"))))
    assert all(not r["baseline"].startswith("ablate_") for r in base)


def test_root_level_terms_are_distinct_in_protocol_and_registry():
    proto = open(os.path.join(ROOT, "ROOT_CAUSE_ADJUDICATION_PROTOCOL_v4.md")).read()
    for term in ("Suffix-stage-specific", "Characterization-specific", "CW-exclusive", "Baseline-exclusive", "never merged"):
        assert term in proto
    reg = list(csv.DictReader(open(os.path.join(ROOT, "MANUSCRIPT_EVIDENCE_REGISTRY.csv"))))
    names = " | ".join(r["metric_name"] for r in reg)
    assert "suffix-stage-specific" in names and "characterization-specific" in names


def test_adjudicator_agreement_statistics():
    from cutwitness.adjudication import agreement_stats
    rows = [{"adjudicator_A_class": a, "adjudicator_B_class": b} for a, b in
            [("latent-continuation", "latent-continuation"), ("final-cut", "final-cut"), ("final-cut", "path-convergence"), ("path-convergence", "path-convergence")]]
    st = agreement_stats(rows)
    assert st["n"] == 4 and st["raw_agreement"] == 0.75 and 0 < st["cohens_kappa"] < 1
    assert agreement_stats([])["raw_agreement"] is None
