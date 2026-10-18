"""Release hygiene v1.5.2: operator documentation never advertises less than the frozen server requirements."""
import os, re
from cutwitness.config import load

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _readme():
    return open(os.path.join(ROOT, "README_FIRST.md")).read()


def test_readme_minimum_matches_frozen_server_requirements():
    req = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))["server_requirements"]
    m = re.search(r"at least (\d+) available vCPUs, (\d+) GiB RAM and (\d+) GiB free disk", _readme())
    assert m, "README must state the minimum server explicitly"
    cpus, ram, disk = map(int, m.groups())
    assert cpus >= req["cpus"] and ram >= req["ram_gb"] and disk >= req["disk_gb"]
    assert (cpus, ram, disk) == (req["cpus"], req["ram_gb"], req["disk_gb"])     # stated exactly, not loosely
    assert f"{req['disk_gb']} GiB is the actual minimum accepted by the frozen S2 server preflight" in _readme()


def test_no_free_disk_figure_below_the_frozen_minimum():
    req = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))["server_requirements"]
    for n in re.findall(r"(\d+)\+?\s*GiB free disk", _readme()):
        assert int(n) >= req["disk_gb"], f"README advertises {n} GiB free disk < {req['disk_gb']}"
    for n in re.findall(r"(\d+)\+?\s*vCPUs?\b[^/]*?(?:,|and)\s*\d+\+?\s*GiB RAM", _readme()):
        assert int(n) >= req["cpus"]


def test_slot_allowance_and_headroom_are_consistent_with_the_duration_gate():
    cfg = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))
    per_slot = cfg["duration_gate"]["per_slot_disk_gib"]
    assert 4 * per_slot <= cfg["server_requirements"]["disk_gb"]
    assert f"{4 * per_slot} GiB corresponds to the four {per_slot}-GiB execution-slot allowances" in _readme()
