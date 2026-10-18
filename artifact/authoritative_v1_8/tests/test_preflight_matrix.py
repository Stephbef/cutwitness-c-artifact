import json, os, subprocess, sys
import pytest
from cutwitness.config import ConfigError, load, validate
from cutwitness.matrix import CLASSES, build_matrix, summarize
from cutwitness.preflight import duration_preflight

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml")
G = 2 ** 30


def test_matrix_classes_counts_and_determinism():
    c = load(CFG); a, b = build_matrix(c), build_matrix(c)
    assert a == b and all(r["unit_class"] in CLASSES for r in a)
    s = summarize(a, 0)
    assert s["SEARCH_TRIALS"] == 588 and s["ABLATION_UNITS"] == 360 and s["SECONDARY_ORACLE_UNITS"] == 9
    assert s["DETERMINISTIC_SUITES"] == 1 and s["NOT_APPLICABLE_UNITS"] == 2 and s["MINIMIZATION_UNITS"] == 3
    reps = {r["rep"] for r in a if r["stage"] == "full" and r["unit_class"] in ("SEARCH_TRIAL", "ABLATION")}
    assert reps == set(range(10))
    na = [r for r in a if r["unit_class"] == "NOT_APPLICABLE"]
    assert all(r["applicability"].startswith("NOT_APPLICABLE: ") for r in na)


def test_duration_gate_pass_and_block_from_measured_resources():
    c = load(CFG)
    ok = duration_preflight(c, {"AVAILABLE_VCPUS": 64, "AVAILABLE_RAM_BYTES": 256 * G, "AVAILABLE_DISK_BYTES": 2000 * G})
    assert ok["EFFECTIVE_SLOTS"] == 4 and ok["CAMPAIGN_DURATION_PREFLIGHT"] == "PASS" and ok["PROJECTED_WALL_DAYS"] <= 45
    three = duration_preflight(c, {"AVAILABLE_VCPUS": 26, "AVAILABLE_RAM_BYTES": 256 * G, "AVAILABLE_DISK_BYTES": 2000 * G})
    assert three["SAFE_CPU_SLOTS"] == 3 and three["CAMPAIGN_DURATION_PREFLIGHT"] == "BLOCKED"
    ram = duration_preflight(c, {"AVAILABLE_VCPUS": 64, "AVAILABLE_RAM_BYTES": 100 * G, "AVAILABLE_DISK_BYTES": 2000 * G})
    assert ram["SAFE_RAM_SLOTS"] == 2 and ram["CAMPAIGN_DURATION_PREFLIGHT"] == "BLOCKED"
    disk = duration_preflight(c, {"AVAILABLE_VCPUS": 64, "AVAILABLE_RAM_BYTES": 256 * G, "AVAILABLE_DISK_BYTES": 50 * G})
    assert disk["SAFE_DISK_SLOTS"] == 0 and disk["CAMPAIGN_DURATION_PREFLIGHT"] == "BLOCKED"
    for k in ("TOTAL_UNITS", "SEARCH_TRIALS", "DETERMINISTIC_SUITES", "MINIMIZATION_UNITS", "SECONDARY_ORACLE_UNITS", "ABLATION_UNITS",
              "NOT_APPLICABLE_UNITS", "TOTAL_SEARCH_SLOT_HOURS", "TOTAL_NONSEARCH_ESTIMATED_SLOT_HOURS", "AVAILABLE_VCPUS",
              "AVAILABLE_RAM_BYTES", "AVAILABLE_DISK_BYTES", "CONFIGURED_MAX_SLOTS", "SAFE_CPU_SLOTS", "SAFE_RAM_SLOTS",
              "SAFE_DISK_SLOTS", "EFFECTIVE_SLOTS", "PROJECTED_WALL_HOURS", "PROJECTED_WALL_DAYS", "EXPECTED_ARTIFACT_COUNT",
              "PROJECTED_ARTIFACT_BYTES", "CAMPAIGN_DURATION_PREFLIGHT"):
        assert k in ok


def test_no_bypass_flag_exists():
    out = subprocess.run([sys.executable, "-m", "cutwitness.one_shot", "--help"], cwd=ROOT, capture_output=True, text=True).stdout
    for flag in ("--force", "--ignore-duration", "--skip", "--bypass"):
        assert flag not in out
    src = open(os.path.join(ROOT, "cutwitness", "controller.py")).read()
    assert "CAMPAIGN_DURATION_PREFLIGHT" in src and "--force" not in src


def test_config_rejects_unfrozen_values():
    c = load(CFG)
    for mutate in (lambda d: d["duration_gate"].__setitem__("max_campaign_days", 60),
                   lambda d: d["full"].__setitem__("trials", 5),
                   lambda d: d.__setitem__("unknown_param", 1)):
        d = json.loads(json.dumps(c)); mutate(d)
        with pytest.raises(ConfigError):
            validate(d)


def test_amendment_recorded_in_config():
    import hashlib
    c = load(CFG); a = c["amendments"][0]
    assert a["version"] == "1.1" and a["sha256"] == hashlib.sha256(open(os.path.join(ROOT, a["path"]), "rb").read()).hexdigest()
    assert c["full"]["budget"] == {"kind": "seconds", "value": 14400} and c["pilot"]["budget"]["value"] == 43200
