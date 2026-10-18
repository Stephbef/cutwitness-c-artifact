"""V1.8 pre-execution amendment: deletion-matched continuation control (RQ2c)."""
import csv, hashlib, os, random, subprocess, sys
import pytest
from cutwitness import pipeline as PL
from cutwitness import suffix as SX
from cutwitness.analysis import latent_endpoint_applicable
from cutwitness.config import load
from cutwitness.matrix import build_matrix, summarize
from cutwitness.model import apply_txn, legal_state, src
from cutwitness.preflight import duration_preflight
from cutwitness.toyengine import ToyEngine
from cutwitness.w3 import gen_history, gen_schema, gen_views

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); G = 1024 ** 3
CFG = lambda: load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))


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


def test_same_length_same_delete_count_every_prefix_legal():
    n = 0
    for s, v, x, key, seed in cases():
        try:
            directed, _ = SX.synthesize(s, v, x, key)
            dm = SX.deletion_matched_suffix(s, v, x, key, directed, random.Random(seed))
        except SX.SuffixUnsupported:
            continue
        assert len(dm) == len(directed) == SX.opportunity_length(s, v, x, key)
        assert sum(map(SX.is_delete_step, dm)) == sum(map(SX.is_delete_step, directed))
        cur = x
        for t in dm:
            cur = apply_txn(cur, t); assert legal_state(s, cur)[0]
        n += 1
    assert n >= 20


def test_order_is_random_not_directed():
    differ = 0
    for s, v, x, key, seed in cases(20):
        try:
            directed, _ = SX.synthesize(s, v, x, key)
            a = SX.deletion_matched_suffix(s, v, x, key, directed, random.Random(seed))
            b = SX.deletion_matched_suffix(s, v, x, key, directed, random.Random(seed + 1000))
        except SX.SuffixUnsupported:
            continue
        differ += [t.delta for t in a] != [t.delta for t in b]
    assert differ > 0


@pytest.mark.parametrize("seed", range(4))
def test_identical_pre_suffix_histories_and_opportunities(seed):
    rng = random.Random(seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6)
    run = lambda tool: PL.run_trial(tool, lambda: ToyEngine(s, vs, "NONE"), ToyEngine.caps, s, vs, h, 8, 2, 0.1, 4242 + seed, minimize_witnesses=False)
    a, b = run("cutwitness_c"), run("ablate_deletion_matched_suffix")
    key = lambda r: (r["history_id"], r["history_length"], r["suffix_length"])
    sa = [key(r) for r in a["execution_log"] if r["executed"] and r["category"] == "search"]
    sb = [key(r) for r in b["execution_log"] if r["executed"] and r["category"] == "search"]
    assert sa == sb and sa
    assert {k: v for k, v in PL.TOOLS["cutwitness_c"].items() if k != "suffix"} == \
           {k: v for k, v in PL.TOOLS["ablate_deletion_matched_suffix"].items() if k != "suffix"}


def test_rng_streams_are_domain_separated_and_deterministic():
    assert PL._delmatched_seed(99, 3) == PL._delmatched_seed(99, 3) != PL._delmatched_seed(99, 4)
    assert PL._delmatched_seed(99, 3) != PL._suffix_seed(99, 3)
    assert latent_endpoint_applicable("ablate_deletion_matched_suffix")


def test_matrix_accounting_and_45_day_gate():
    c = CFG(); rows = build_matrix(c)
    dm = [r for r in rows if r["tool"] == "ablate_deletion_matched_suffix"]
    assert len(dm) == 90 and all(r["unit_class"] == "ABLATION" and r["budget_value"] == 14400 for r in dm)
    cw = {(r["target"], r["workload"], r["rep"]): r["seed"] for r in rows if r["tool"] == "cutwitness_c" and r["stage"] == "full"}
    assert all(r["seed"] == cw[(r["target"], r["workload"], r["rep"])] for r in dm)
    assert all(r["tool"] != "ablate_deletion_matched_suffix" for r in rows if r["stage"] == "pilot")
    s = summarize(rows, c["duration_gate"]["overhead_hours"])
    assert (s["TOTAL_UNITS"], s["ABLATION_UNITS"]) == (963, 360)
    assert s["TOTAL_SEARCH_SLOT_HOURS"] + s["TOTAL_NONSEARCH_ESTIMATED_SLOT_HOURS"] == 4200 <= 4 * 45 * 24
    ok = duration_preflight(c, {"AVAILABLE_VCPUS": 64, "AVAILABLE_RAM_BYTES": 256 * G, "AVAILABLE_DISK_BYTES": 2048 * G})
    assert ok["CAMPAIGN_DURATION_PREFLIGHT"] == "PASS" and ok["PROJECTED_WALL_DAYS"] == 43.75
    bad = duration_preflight(c, {"AVAILABLE_VCPUS": 26, "AVAILABLE_RAM_BYTES": 256 * G, "AVAILABLE_DISK_BYTES": 2048 * G})
    assert bad["CAMPAIGN_DURATION_PREFLIGHT"] == "BLOCKED"


def test_rq2c_is_a_separate_family_and_spec_v7_is_pinned():
    c = CFG(); fam = c["analysis_spec"]["ablation_families"]
    assert fam["ablate_deletion_matched_suffix"] == {"rq": "RQ2c", "primary_metric": "matched_pair_exact_sign_test", "inferential": True, "paired": True}
    assert fam["ablate_random_suffix"]["rq"] == "RQ2b"
    assert c["analysis_spec"]["version"] == "7"
    assert c["analysis_spec"]["sha256"] == hashlib.sha256(open(os.path.join(ROOT, c["analysis_spec"]["path"]), "rb").read()).hexdigest()


def test_one_shot_writes_rq2c_and_keeps_rq2b_outputs(tmp_path):
    d = str(tmp_path / "run")
    assert subprocess.run([sys.executable, "-m", "cutwitness.one_shot", "--config", os.path.join(ROOT, "campaign", "CRASHTEST_SIMULATION.yaml"),
                           "--run-dir", d], cwd=ROOT, capture_output=True).returncode == 0
    a = os.path.join(d, "analysis", "SYNTHETIC_ENGINEERING")
    b = next(csv.reader(open(os.path.join(a, "rq2b_matched_summary.csv"))))
    assert "holm_p_within_rq2b" in b
    c = next(csv.reader(open(os.path.join(a, "rq2c_matched_summary.csv"))))
    assert "holm_p_within_rq2c" in c
    assert "deletion_matched_unit_id" in next(csv.reader(open(os.path.join(a, "rq2c_matched_pairs.csv"))))


def test_witness_closure_keeps_v172_owner_order():
    from cutwitness.controller import closure_order
    units = [{"tool": t, "unit_id": f"full|feldera|W1|{t}|0"} for t in
             ("ablate_deletion_matched_suffix", "ablate_random_suffix", "cutwitness_c", "ablate_no_suffix", "baseline_random_te")]
    order = [u["tool"] for u in sorted(units, key=closure_order)]
    assert order[-1] == "ablate_deletion_matched_suffix"
    v172 = [u["tool"] for u in sorted([u for u in units if u["tool"] != "ablate_deletion_matched_suffix"], key=lambda z: z["unit_id"])]
    assert order[:-1] == v172
