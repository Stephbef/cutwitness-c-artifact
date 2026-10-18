"""Nine-point crash/resume matrix: every resumed run must equal the uninterrupted reference run."""
import collections, json, os, subprocess, sys
import pytest
from cutwitness.campaign import Journal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "campaign", "CRASHTEST_SIMULATION.yaml")
POINTS = ["before_unit_start", "after_running_entry", "during_target_execution", "after_output_before_commit",
          "during_journal_append", "after_commit", "between_pilot_and_full", "during_analysis", "during_artifact_closure"]


def run(run_dir, crash=None):
    env = dict(os.environ); env.pop("CW_CRASH_AT", None)
    if crash:
        env["CW_CRASH_AT"] = crash
    return subprocess.run([sys.executable, "-m", "cutwitness.one_shot", "--config", CFG, "--run-dir", run_dir],
                          cwd=ROOT, env=env, capture_output=True, text=True).returncode


def material(run_dir):
    out = {}
    for d, _, fs in os.walk(run_dir):
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), run_dir)
            if rel.startswith(("results", "witnesses", "analysis", "data")) or rel == "SHA256SUMS":
                out[rel] = open(os.path.join(d, f), "rb").read()
    return out


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("ref"))
    assert run(d) == 0
    v = json.load(open(os.path.join(d, "FINAL_VERDICT.json")))
    assert v["verdict"] == "COMPLETE_FULL_CAMPAIGN", v
    return d, v


@pytest.mark.parametrize("point", POINTS)
def test_crash_then_resume_equals_uninterrupted(reference, tmp_path, point):
    ref_dir, ref_v = reference; d = str(tmp_path / "run")
    assert run(d, point) == 77, f"crash point {point} was not reached"
    rid = json.load(open(os.path.join(d, "run_meta.json")))["run_id"]
    assert run(d) == 0
    v = json.load(open(os.path.join(d, "FINAL_VERDICT.json")))
    assert v["verdict"] == ref_v["verdict"] and v["results_digest"] == ref_v["results_digest"]
    assert v["run_id"] == rid, "run_id must not change across resume"
    assert material(d) == material(ref_dir), "scientifically material outputs differ"
    j = Journal(os.path.join(d, "journal.jsonl")); assert j.verify()[0]
    commits = collections.Counter(r["payload"]["unit_id"] for r in j.recs if r["kind"] == "UNIT" and r["payload"]["status"] == "COMMITTED")
    assert commits and max(commits.values()) == 1, "duplicate COMMITTED unit"
    seeds = collections.defaultdict(set)
    for r in j.recs:
        if r["kind"] == "UNIT" and r["payload"]["status"] == "RUNNING":
            seeds[r["payload"]["unit_id"]].add(r["payload"]["seed"])
    assert all(len(s) == 1 for s in seeds.values()), "seed substituted on retry"
    if point == "during_journal_append":
        assert any(r["kind"] == "TORN_TAIL_RECOVERED" for r in j.recs)
