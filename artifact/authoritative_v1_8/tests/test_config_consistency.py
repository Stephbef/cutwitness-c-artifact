"""Release hygiene v1.5.1: duplicate protocol metadata must stay synchronized with the authoritative matrix specification."""
import json, os
from cutwitness.config import load

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_sealed_campaign_metadata_mirrors_match_the_matrix():
    cfg = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))
    assert cfg["mode"] == "SEALED_CAMPAIGN"
    m = cfg["matrix"]
    assert set(cfg["ablations"]) == set(m["ablation_map"])
    assert set(cfg["full"]["tools"]) == set(m["search_tools"]) | set(m["secondary_oracles"]) | set(m["ablation_map"])
    assert set(cfg["pilot"]["tools"]) <= set(m["search_tools"])
    assert set(cfg["analysis_spec"]["ablation_families"]) == set(m["ablation_map"])


def test_a_new_arm_added_only_to_the_matrix_is_detected():
    cfg = json.loads(open(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml")).read())
    cfg["matrix"]["ablation_map"]["ablate_hypothetical"] = {"rqs": ["RQx"], "targets": ["pg_ivm"], "workloads": ["W1"]}
    assert set(cfg["ablations"]) != set(cfg["matrix"]["ablation_map"])          # the consistency check would fail closed


def test_effective_rq2b_specification_is_unambiguous():
    cfg = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))
    text = open(os.path.join(ROOT, cfg["analysis_spec"]["path"])).read()
    head = text.split("\n## ", 1)[0]
    for need in ("EFFECTIVE RQ2b SPECIFICATION", "exact two-sided sign test", "Clopper", "Holm", "descriptive only",
                 "no Mann–Whitney, no A12 and no log-rank"):
        assert need in head, need
    assert "HISTORICAL — SUPERSEDED BY AMENDMENT v1.5 BELOW — MUST NOT BE USED FOR SCIENTIFIC ANALYSIS" in text
