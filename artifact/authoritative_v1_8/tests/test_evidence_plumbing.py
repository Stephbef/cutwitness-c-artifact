"""Patch-2: every manuscript metric has a producer; instrumentation never changes search behaviour."""
import collections, csv, hashlib, json, os, random, subprocess, sys
import pytest
from cutwitness.config import load
from cutwitness.model import Schema, Table, Txn, ZSet, sha
from cutwitness.pipeline import TOOLS, run_trial
from cutwitness.toyengine import ToyEngine
from cutwitness.w3 import gen_history, gen_schema, gen_views

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(ROOT, "tests", "fixtures")


def _trial(tool, fault, seed=41, budget=5):
    rng = random.Random(seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6)
    made = [0]
    def fac():
        made[0] += 1; return ToyEngine(s, vs, fault)
    r = run_trial(tool, fac, ToyEngine.caps, s, vs, h, budget, 2, 0.1, 1234, minimize_witnesses=False)
    return r, made[0]


def test_instrumentation_preserves_search_behaviour_fingerprints():
    ref = json.load(open(os.path.join(FX, "pre_patch2_trial_digests.json")))
    for key, v in ref.items():
        tool, fault = key.split("|")
        r, _ = _trial(tool, fault)
        assert sha({k: r[k] for k in v["keys"]}) == v["digest"], key


@pytest.fixture(scope="module")
def crashrun(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("p2") / "run")
    rc = subprocess.run([sys.executable, "-m", "cutwitness.one_shot", "--config", os.path.join(ROOT, "campaign", "CRASHTEST_SIMULATION.yaml"),
                         "--run-dir", d], cwd=ROOT, capture_output=True).returncode
    assert rc == 0
    return d


def test_campaign_unit_fingerprints_preserved(crashrun):
    from cutwitness.campaign import Journal
    ref = json.load(open(os.path.join(FX, "pre_patch2_crashtest_units.json")))
    j = Journal(os.path.join(crashrun, "journal.jsonl")); seen = 0
    for r in j.recs:
        if r["kind"] == "UNIT" and r["payload"]["status"] == "COMMITTED" and r["payload"]["unit_id"] in ref:
            u = json.load(open(os.path.join(crashrun, "results", r["payload"]["result"] + ".json")))
            v = ref[r["payload"]["unit_id"]]
            assert sha({k: u[k] for k in v["keys"]}) == v["digest"], r["payload"]["unit_id"]; seen += 1
    assert seen == len(ref)


@pytest.mark.parametrize("tool", ["cutwitness_c", "baseline_random_te", "baseline_zippy", "ablate_no_reduction"])
def test_every_execution_recorded_exactly_once(tool):
    r, made = _trial(tool, "F2_LOST_DELETE")
    executed = [x for x in r["execution_log"] if x["executed"]]
    assert len(executed) == made, "one execution row per target instantiation, no more, no fewer"
    assert len({x["seq"] for x in r["execution_log"]}) == len(r["execution_log"])
    assert r["histories_executed"] == sum(1 for x in executed if x["category"] in ("search", "path_pair"))
    assert all(not x["executed"] for x in r["execution_log"] if x["outcome"] in ("PRUNED_EQUIVALENT", "NOT_SELECTED"))


def test_latent_ttf_ignores_non_latent_and_censors():
    s = Schema([Table("t0", [("id", "int", False), ("k", "int", False), ("v", "dec", True), ("s", "text", False)], pk=[0])])
    r, _ = _trial("cutwitness_c", "F2_LOST_DELETE")
    if r["first_candidate_at"] is not None and all(not d["latent"] for d in r["divergences"] if d["triage"].get("candidate")):
        assert r["first_latent_candidate_at"] is None and r["latent_censored"]
    r9, _ = _trial("cutwitness_c", "F9_LATENT_RESIDUAL")
    lat = [d for d in r9["divergences"] if d["triage"].get("candidate") and d["latent"]]
    assert (r9["first_latent_candidate_at"] is None) == (not lat) == r9["latent_censored"]
    if lat:
        assert r9["first_latent_candidate_at"] >= r9["first_candidate_at"]
    rn, _ = _trial("cutwitness_c", "NONE")
    assert rn["latent_censored"] and rn["first_latent_candidate_at"] is None


def test_latent_csv_censoring_and_budget(crashrun):
    rows = list(csv.DictReader(open(os.path.join(crashrun, "analysis", "SYNTHETIC_ENGINEERING", "latent_ttf_event.csv"))))
    assert rows
    na = [r for r in rows if r["latent_endpoint"] == "NOT_APPLICABLE_BY_DESIGN"]
    assert na and all(r["first_latent_time"].startswith("N/A") and r["censored"].startswith("N/A") for r in na)
    for r in [x for x in rows if x["latent_endpoint"] == "APPLICABLE"]:
        if r["censored"] == "True":
            assert r["first_latent_time"] == r["budget"] and not r["witness_id"]
        else:
            assert float(r["first_latent_time"]) <= float(r["budget"]) and r["witness_id"]


def test_histories_and_lifecycle_csv_consistency(crashrun):
    a = os.path.join(crashrun, "analysis", "SYNTHETIC_ENGINEERING")
    he = list(csv.DictReader(open(os.path.join(a, "histories_executed.csv"))))
    keys = collections.Counter((r["unit_id"], r["exec_index"]) for r in he)
    assert he and max(keys.values()) == 1
    summ = list(csv.DictReader(open(os.path.join(a, "histories_executed_summary.csv"))))
    for s_ in summ:
        n = sum(1 for r in he if r["unit_id"] == s_["unit_id"] and r["executed"] == "True" and r["category"] in ("search", "path_pair"))
        assert n == int(s_["histories_executed"])
    lce = list(csv.DictReader(open(os.path.join(a, "lifecycle_events.csv"))))
    assert all(r["event_type"] != "UPGRADE" and r["support"] == "SUPPORTED" for r in lce)


def test_minimizer_calls_deterministic(tmp_path):
    from cutwitness import controller
    from decimal import Decimal as D
    from cutwitness.refmodel import GroupAgg, Scan, View
    cfg = load(os.path.join(ROOT, "campaign", "CRASHTEST_SIMULATION.yaml"))
    s = Schema([Table("t0", [("id", "int", False), ("k", "int", False), ("v", "dec", True)], pk=[0])])
    v = View("v", GroupAgg("g", Scan("s", "t0", 3), [1], [("COUNT", None), ("SUM", 2)]))
    h = [Txn({"t0": ZSet([((i, 3, D(i)), 1)])}).canon() for i in range(1, 6)]
    cfg["targets"]["pg_ivm"]["fault"] = "F1_WRONG_MULT"
    d = {"triage": {"candidate": True, "class": "TARGET_MAINTENANCE_BUG"}, "history_digest": "h", "history": h, "suffix": [], "where": "cut"}
    from cutwitness.oracles import judge
    from cutwitness.model import history_from_canon
    fac = lambda: ToyEngine(s, [v], "F1_WRONG_MULT")
    d["obs_digest"] = judge(fac, s, [v], history_from_canon(h), []).get("obs_digest")
    unit = {"unit_id": "u", "target": "pg_ivm", "workload": "W3", "tool": "cutwitness_c", "schema": s.to_json(), "views": [v.to_json()], "divergences": [d]}
    a = controller.witness_closure(cfg, str(tmp_path / "a"), [unit]); b = controller.witness_closure(cfg, str(tmp_path / "b"), [unit])
    assert a[0]["minimizers"] == b[0]["minimizers"] and a[0]["status"] == "NEW"
    for m in a[0]["minimizers"]:
        assert m["wall_time_s"] is None and m["predicate_calls_target"] <= m["predicate_calls_logical"] and m["replay_success"]


def test_ablation_families_frozen_and_specified():
    cfg = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))
    spec = cfg["analysis_spec"]
    assert hashlib.sha256(open(os.path.join(ROOT, spec["path"]), "rb").read()).hexdigest() == spec["sha256"]
    assert set(spec["ablation_families"]) == set(cfg["matrix"]["ablation_map"])
    assert spec["ablation_families"]["ablate_no_suffix"]["inferential"] is False and spec["path"].endswith("_v7.md")
    text = open(os.path.join(ROOT, spec["path"])).read()
    for fam, v in spec["ablation_families"].items():
        assert fam in text and v["rq"] in text
    ev = cfg["evidence"]["adjudication_protocol"]
    assert ev["path"].endswith("_v4.md")
    assert hashlib.sha256(open(os.path.join(ROOT, ev["path"]), "rb").read()).hexdigest() == ev["sha256"]


def test_adjudication_ledger_schema():
    from cutwitness.adjudication import LEDGER_COLUMNS, validate_external, validate_ledger
    W = {"w1": {"id": "w1", "status": "NEW", "target": "pg_ivm"}, "w2": {"id": "w2", "status": "NEW", "target": "pg_ivm"},
         "w3": {"id": "w3", "status": "NEW", "target": "feldera"}, "w4": {"id": "w4", "status": "DEMOTED_NONDETERMINISM", "target": "pg_ivm"}}
    def row(**k):
        r = {c: "" for c in LEDGER_COLUMNS}
        r.update({"root_cause_id": "R1", "witness_ids": "w1", "target": "pg_ivm", "primary_class": "latent-continuation", "latent": "true",
                  "adjudication_basis": "same residual after group death", "confidence_status": "ADJUDICATED",
                  "latent_attribution": "HISTORY_CONDITIONED_LATENT", "adjudicator_A_class": "latent-continuation",
                  "adjudicator_B_class": "latent-continuation", "agreement": "AGREE", "resolution": "", "adjudicator_independence": "AUTHORS_ONLY"})
        r.update(k); return r
    assert validate_ledger([row()], W) == []
    assert validate_ledger([row(witness_ids="w1;w2", merge_evidence="same per-key SUM state after death in both minimal histories")], W) == []
    assert validate_ledger([row(witness_ids="w1;w2", merge_evidence="")], W)
    assert validate_ledger([row(witness_ids="w1;w2", merge_evidence="operator family")], W)
    assert validate_ledger([row(witness_ids="w1;w3", merge_evidence="x y z")], W)
    assert validate_ledger([row(witness_ids="w9")], W) and validate_ledger([row(witness_ids="w4")], W)
    assert validate_ledger([row(), row(root_cause_id="R2")], W)
    assert validate_ledger([row(primary_class="bug")], W)
    assert validate_ledger([row(latent_attribution="NOT_LATENT")], W)            # latent=true needs an attribution class
    assert validate_ledger([row(latent="false", latent_attribution="NOT_LATENT")], W) == []
    assert validate_ledger([row(agreement="DISAGREE", adjudicator_B_class="final-cut")], W)        # needs a resolution
    assert validate_ledger([row(agreement="DISAGREE", adjudicator_B_class="final-cut", resolution="kept separate (rule F)")], W) == []
    assert validate_ledger([row(adjudicator_independence="")], W)
    assert validate_external([{"report_id": "X", "root_cause_ids": "R9", "target": "pg_ivm", "tracker_reference": "", "status": "FIXED",
                               "status_date": "", "note": ""}], {"R1"})


def test_registry_has_exactly_one_replacement_path_and_producers_exist(crashrun):
    from cutwitness.adjudication import validate_registry
    rows = list(csv.DictReader(open(os.path.join(ROOT, "MANUSCRIPT_EVIDENCE_REGISTRY.csv"))))
    assert rows and all(r["replacement_rule"] for r in rows) and validate_registry(rows) == []
    assert any(r["producer_status"] == "POST-RUN MANUAL/ADJUDICATED" for r in rows)
    assert len({(r["manuscript_location"], r["metric_name"]) for r in rows}) == len(rows)
    produced = set(os.listdir(os.path.join(crashrun, "analysis", "SYNTHETIC_ENGINEERING")))
    for r in rows:
        if r["producer_status"] == "EXISTS":
            for part in r["analysis_artifact"].replace(",", " ").split():
                if part.endswith((".csv", ".svg")) and "<" not in part and part not in ("CAMPAIGN_MATRIX.csv",):
                    assert part.split("/")[-1] in produced, part
    fp = json.load(open(os.path.join(crashrun, "preseal", "S1_fingerprint.json")))
    for k in ("cpu_model", "cpus", "ram_bytes", "disk_free_bytes", "kernel", "docker_server_version"):
        assert k in fp
