import json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cutwitness.campaign import Campaign, Journal, JournalCorruption, RunLock, hmac_seed
from cutwitness.stats import a12, holm, kaplan_meier, logrank, bootstrap_ci, ratio_of_medians
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_hmac_seed_deterministic():
    assert hmac_seed("m", "a", 1) == hmac_seed("m", "a", 1) != hmac_seed("m", "a", 2)


def test_journal_chain_and_tamper_detection(tmp_path):
    j = Journal(str(tmp_path / "j.jsonl"))
    for i in range(5):
        j.append("X", {"i": i})
    assert Journal(str(tmp_path / "j.jsonl")).verify()[1] == 5
    lines = open(tmp_path / "j.jsonl").read().splitlines()
    rec = json.loads(lines[2]); rec["payload"]["i"] = 99; lines[2] = json.dumps(rec)
    open(tmp_path / "j.jsonl", "w").write("\n".join(lines) + "\n")
    with pytest.raises(JournalCorruption):
        Journal(str(tmp_path / "j.jsonl"))


def test_config_change_after_seal_refused(tmp_path):
    c = Campaign(str(tmp_path), {"a": 1}); rid = c.ensure_run_id()
    assert Campaign(str(tmp_path), {"a": 1}).ensure_run_id() == rid
    with pytest.raises(RuntimeError):
        Campaign(str(tmp_path), {"a": 2}).ensure_run_id()


def test_lock_exclusive(tmp_path):
    with RunLock(str(tmp_path / ".lock")):
        with pytest.raises(RuntimeError):
            with RunLock(str(tmp_path / ".lock")):
                pass


CRASH = r'''
import sys, os
sys.path.insert(0, ROOT)
from cutwitness.campaign import Campaign
c = Campaign(RUN, {"cfg": 1}); c.ensure_run_id()
units = [{"unit_id": f"u{i}", "seed": i} for i in range(6)]
def ex(u):
    if u["unit_id"] == CRASH_AT and os.environ.get("CRASH") == "1":
        os._exit(9)
    return {"u": u["unit_id"], "v": u["seed"] * 2}
c.run_units(units, ex)
'''


@pytest.mark.parametrize("crash_at", ["u0", "u3", "u5"])
def test_crash_resume_no_duplicate_commits(tmp_path, crash_at):
    run = str(tmp_path / "run")
    code = CRASH.replace("ROOT", repr(ROOT)).replace("RUN", repr(run)).replace("CRASH_AT", repr(crash_at))
    p = subprocess.run([sys.executable, "-c", code], env={**os.environ, "CRASH": "1"})
    assert p.returncode == 9
    p = subprocess.run([sys.executable, "-c", code], env={**os.environ, "CRASH": "0"})
    assert p.returncode == 0
    c = Campaign(run, {"cfg": 1}); st = c.status()
    assert all(st[f"u{i}"]["status"] == "COMMITTED" for i in range(6))
    commits = [r for r in c.journal.recs if r["kind"] == "UNIT" and r["payload"]["status"] == "COMMITTED"]
    assert len(commits) == 6
    interrupted = [r for r in c.journal.recs if r["kind"] == "UNIT" and r["payload"].get("reason") == "interrupted"]
    assert len(interrupted) == 1 and c.journal.verify()[0]
    seeds = [r["payload"]["seed"] for r in c.journal.recs if r["kind"] == "UNIT" and r["payload"]["status"] == "RUNNING"]
    assert seeds.count(int(crash_at[1:])) == 2  # same seed on retry, never substituted


def test_stats_known_values():
    assert a12([2, 3], [1, 1]) == 1.0 and a12([1], [1]) == 0.5
    assert holm([0.01, 0.04]) == [0.02, 0.04]
    assert kaplan_meier([1, 2, 3], [1, 1, 0])[-1][1] == pytest.approx(1 / 3)
    assert logrank([1, 2, 3], [1, 1, 1], [1, 2, 3], [1, 1, 1]) == pytest.approx(1.0)
    lo, hi = bootstrap_ci([1, 2, 3, 4, 5], n=500); assert lo <= 3 <= hi
    assert ratio_of_medians([2, 4], [1, 2]) == 2.0


def test_one_shot_fails_closed_when_not_sealed(tmp_path):
    cfg = {"release_state": "BLOCKED_NOT_SEALED", "full": {"targets": ["pg_ivm"]}}
    cp = tmp_path / "c.yaml"; cp.write_text(json.dumps(cfg))
    p = subprocess.run([sys.executable, "-m", "cutwitness.one_shot", "--config", str(cp), "--run-dir", str(tmp_path / "r")], cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 3
    v = json.load(open(tmp_path / "r" / "FINAL_VERDICT.json"))
    assert v["verdict"] == "NOT_STARTED_OPERATIONAL"
