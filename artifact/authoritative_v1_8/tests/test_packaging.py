"""Packaging: manifest generation, verification, tamper detection and wrapper fail-closed behaviour, on a temporary copy."""
import os, shutil, subprocess, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


@pytest.fixture(scope="module")
def pkg(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("pkg") / "cw")
    shutil.copytree(ROOT, d, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", ".pytest_cache", "runs", "*.pyc"))
    for f in ("SHA256SUMS", os.path.join("manifests", "PREEXECUTION_MANIFEST.json")):
        p = os.path.join(d, f)
        if os.path.exists(p):
            os.remove(p)
    r = subprocess.run([sys.executable, "tools/make_manifest.py"], cwd=d, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return d


def verify(d):
    return subprocess.run([sys.executable, "tools/verify_package.py"], cwd=d, capture_output=True, text=True)


def test_manifest_and_sha256sums_verify(pkg):
    r = verify(pkg); assert r.returncode == 0 and "PASS" in r.stdout
    sums = open(os.path.join(pkg, "SHA256SUMS")).read().splitlines()
    import hashlib
    for line in sums:
        h, p = line.split("  ", 1)
        assert hashlib.sha256(open(os.path.join(pkg, p), "rb").read()).hexdigest() == h


def test_tampering_and_unlisted_files_are_rejected(pkg, tmp_path):
    d = str(tmp_path / "t"); shutil.copytree(pkg, d)
    with open(os.path.join(d, "cutwitness", "pilot.py"), "a") as f:
        f.write("\n# tampered\n")
    assert verify(d).returncode == 2
    d2 = str(tmp_path / "u"); shutil.copytree(pkg, d2)
    open(os.path.join(d2, "cutwitness", "extra.py"), "w").write("x = 1\n")
    assert verify(d2).returncode == 2


def test_manifest_records_required_digests(pkg):
    import json
    m = json.load(open(os.path.join(pkg, "manifests", "PREEXECUTION_MANIFEST.json")))
    for k in ("repository_tree", "active_source", "test_suite", "campaign_config", "dependency_lock", "target_freeze",
              "scientific_freeze", "one_shot_amendment", "feasibility_amendment_v1_1"):
        assert len(m["digests"][k]) == 64
    assert all(e["path"] != ".git" and not e["path"].startswith(".git/") for e in m["files"])


def test_wrapper_fails_closed_before_any_campaign_state(pkg, tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("CUTWITNESS_W1_TOKEN", "MOBILITY_DB_TOKEN")}
    run_dir = str(tmp_path / "r")
    r = subprocess.run(["bash", "run_one_shot.sh", run_dir], cwd=pkg, env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 3
    assert not os.path.exists(os.path.join(run_dir, "journal.jsonl")) and not os.path.exists(os.path.join(run_dir, "run_meta.json"))
    import json
    assert json.load(open(os.path.join(run_dir, "FINAL_VERDICT.json")))["verdict"] == "NOT_STARTED_OPERATIONAL"
