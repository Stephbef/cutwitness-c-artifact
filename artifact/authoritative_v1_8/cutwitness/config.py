"""Frozen campaign configuration: schema validation and canonical hashing (no scientific defaults elsewhere)."""
from __future__ import annotations
import json
from .model import cjson, sha

REQUIRED = {
    "schema_version": str, "mode": str, "release_state": str, "code_tree_digest": str, "scientific_freeze_digest": str,
    "one_shot_amendment_digest": str, "master_seed": str, "hmac": str, "targets": dict, "upgrade_pairs": dict,
    "workloads": dict, "operator_subset": list, "capability_matrix": dict, "k": int, "sta_version": str, "rho": float,
    "transformations": dict, "baselines": list, "ablations": list, "pilot": dict, "full": dict, "timeouts": dict,
    "resources": dict, "oracles": list, "triage": dict, "bug_statuses": list, "statistics": dict, "output_schemas": dict,
    "artifact": dict, "server_requirements": dict, "w1_token_env": str, "nondet_reruns": int, "demotion_rule": str,
    "witness_closure": dict, "operational_retries": int, "tester_conformance": dict,
    "matrix": dict, "duration_gate": dict, "amendments": list, "analysis_spec": dict, "evidence": dict,
}
MODES = ("SEALED_CAMPAIGN", "ENGINEERING_SIMULATION")
PILOT_KEYS = {"targets": list, "workloads": list, "tools": list, "trials": int, "budget": dict, "signals": dict}
FULL_KEYS = {"targets": list, "workloads": list, "tools": list, "trials": int, "budget": dict}


class ConfigError(Exception):
    pass


def validate(cfg: dict) -> str:
    for k, t in REQUIRED.items():
        if k not in cfg:
            raise ConfigError(f"missing key {k}")
        if not isinstance(cfg[k], t) or (t is int and isinstance(cfg[k], bool)):
            raise ConfigError(f"{k} must be {t.__name__}")
    extra = set(cfg) - set(REQUIRED)
    if extra:
        raise ConfigError(f"unregistered keys {sorted(extra)}")
    if cfg["mode"] not in MODES:
        raise ConfigError("mode")
    for sect, keys in (("pilot", PILOT_KEYS), ("full", FULL_KEYS)):
        for k, t in keys.items():
            if not isinstance(cfg[sect].get(k), t):
                raise ConfigError(f"{sect}.{k} must be {t.__name__}")
    for k in ("budget",):
        for sect in ("pilot", "full"):
            b = cfg[sect][k]
            if set(b) != {"kind", "value"} or b["kind"] not in ("executions", "seconds"):
                raise ConfigError(f"{sect}.budget")
    m = cfg["matrix"]
    for k in ("search_tools", "ablation_map", "secondary_oracles", "deterministic_suites", "minimization"):
        if k not in m:
            raise ConfigError(f"matrix.{k}")
    if cfg["full"]["trials"] < 10 and cfg["mode"] == "SEALED_CAMPAIGN":
        raise ConfigError("stochastic repetitions must stay >= 10")
    fam = cfg["analysis_spec"].get("ablation_families", {})
    if set(fam) != set(cfg["matrix"]["ablation_map"]) and cfg["mode"] == "SEALED_CAMPAIGN":
        raise ConfigError("every pre-declared ablation needs exactly one frozen analysis family")
    if cfg["evidence"].get("timing_mode") not in ("logical", "wallclock"):
        raise ConfigError("evidence.timing_mode")
    if cfg["duration_gate"].get("max_campaign_days") != 45:
        raise ConfigError("duration_gate.max_campaign_days is frozen at 45")
    for t in cfg["pilot"]["targets"] + cfg["full"]["targets"]:
        if t not in cfg["targets"]:
            raise ConfigError(f"unknown target {t}")
    sig = cfg["pilot"]["signals"]
    for k in ("A", "B_speedup", "B_a12", "D_coverage_ratio"):
        if k not in sig:
            raise ConfigError(f"pilot.signals.{k}")
    if cfg["mode"] == "SEALED_CAMPAIGN" and any(v.get("kind") != "real" for v in cfg["targets"].values()):
        raise ConfigError("sealed campaign must use real targets only")
    if cfg["mode"] == "ENGINEERING_SIMULATION" and any(v.get("kind") != "simulated" for v in cfg["targets"].values()):
        raise ConfigError("engineering simulation must use simulated targets only")
    return digest(cfg)


def digest(cfg: dict) -> str:
    return sha(cfg)


def load(path: str) -> dict:
    with open(path) as f:
        cfg = json.load(f)  # canonical JSON is a YAML 1.2 subset
    validate(cfg)
    return cfg


def canonical_text(cfg: dict) -> str:
    return json.dumps(cfg, sort_keys=True, indent=1, ensure_ascii=True) + "\n"
