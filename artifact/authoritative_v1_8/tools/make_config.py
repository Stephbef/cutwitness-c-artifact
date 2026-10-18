"""Generate the two canonical configurations from the frozen parameters below (run before packaging)."""
import hashlib, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from cutwitness.adapters.feldera import FelderaAdapter
from cutwitness.adapters.pgwire import PgIvmAdapter, RisingWaveAdapter
from cutwitness.config import canonical_text, validate
from cutwitness.controller import code_digest
from cutwitness.oracles import TRIAGE_ORDER
from cutwitness.pipeline import TOOLS
from cutwitness.toyengine import FAULTS
from cutwitness.transforms import CLASS

h = lambda p: hashlib.sha256(open(os.path.join(ROOT, p), "rb").read()).hexdigest()
MATRIX = {"pg_ivm": PgIvmAdapter(None, [], None, None, {}, {}, "x").capability_matrix(),
          "risingwave": RisingWaveAdapter(None, [], None, None, {}, {}, "x").capability_matrix(),
          "feldera": FelderaAdapter(None, [], None, None, {}, {}, "x").capability_matrix()}
for m in MATRIX.values():
    m.pop("target")
BASELINES = ["baseline_random_clean", "baseline_random_te", "baseline_stateful_fuzz", "baseline_zippy", "baseline_source_por", "baseline_tlp"]
# Non-authoritative metadata mirrors (`ablations`, `full.tools`): execution reads matrix.* and pilot.tools only.
# Kept synchronized with matrix.ablation_map (enforced by tests/test_config_consistency.py).
ABLATIONS = ["ablate_no_suffix", "ablate_no_guidance", "ablate_no_reduction", "ablate_random_lifecycle", "ablate_random_suffix", "ablate_deletion_matched_suffix"]
COMMON = {
    "schema_version": "cutwitness-c/1", "code_tree_digest": code_digest(ROOT),
    "scientific_freeze_digest": h("science/SCIENTIFIC_FREEZE_CUTWITNESS_C.md"),
    "one_shot_amendment_digest": h("science/ONE_SHOT_EXECUTION_AMENDMENT.md"),
    "master_seed": "cutwitness-c/master-seed/published-2026-10-15/7d2c9e41",
    "hmac": "HMAC-SHA256(master_seed, '|'.join(parts)) first 8 bytes, big-endian",
    "upgrade_pairs": {"note": "UPGRADE excluded: every target runs its newest pinned release; no newer pinned release exists"},
    "operator_subset": ["select", "project", "inner_equijoin", "left_outer_equijoin", "group_by_count_sum_avg_min_max", "distinct", "per_partition_topk"],
    "capability_matrix": MATRIX, "k": 2, "sta_version": "sta/1", "rho": 0.10, "transformations": CLASS,
    "baselines": BASELINES + ["ddmin_witness_comparison", "target_native_suites_at_S4"], "ablations": ABLATIONS,
    "timeouts": {"sql_s": 120, "ready_s": 300, "stop_s": 60, "lifecycle_s": 600, "compile_s": 1800, "barrier_s": 600, "pull_s": 3600},
    "oracles": ["O1_clean_rebuild", "O2_path_vs_path", "O3_duckdb_reference", "O4_per_step_continuation"],
    "triage": {"order": TRIAGE_ORDER, "candidate_requires": {"reproductions": 2, "nondet_reruns_identical": 10, "o3_agrees_with_reference": True}},
    "bug_statuses": ["NEW", "DUPLICATE", "KNOWN", "INVALID", "EXPECTED", "ACKNOWLEDGED", "FIXED", "UNRESOLVED"],
    "statistics": {"bootstrap_resamples": 10000, "bootstrap_seed": 0, "alpha": 0.05, "mann_whitney": "two-sided asymptotic, continuity and tie corrected",
                   "multiplicity": "Holm over CutWitness-C vs each baseline per target", "censoring": "time to first candidate right-censored at budget",
                   "survival": "Kaplan-Meier", "survival_test": "log-rank", "effect_sizes": ["A12", "ratio_of_medians"]},
    "output_schemas": {"unit_result": "cutwitness-c/unit/1", "witness": "cutwitness-c/witness/1", "verdict": "cutwitness-c/verdict/1"},
    "artifact": {"sha256sums": True, "raw_gtfs_redistribution": "by license_class only"},
    "w1_token_env": "CUTWITNESS_W1_TOKEN", "nondet_reruns": 10,
    "demotion_rule": "S8 re-executes every candidate nondet_reruns times in fresh sessions; any observation digest differing from the recorded one demotes it to TARGET_NONDETERMINISM",
    "witness_closure": {"min_budget": 400}, "operational_retries": 2,
}
AMEND = "science/CUTWITNESS_C_PREEXECUTION_FEASIBILITY_AMENDMENT_v1_1.md"
COMMON["amendments"] = [{"version": "1.1", "path": AMEND, "sha256": h(AMEND), "pre_amendment_commit": "a859cc3",
                         "pre_amendment_config_digest": "36e24c592a173a1f26a492b782f744b2a8ac3afbb3ff0bf5fbd90e24b2c19ba6"}]
MATRIX_SPEC = {"search_tools": ["cutwitness_c", "baseline_random_clean", "baseline_random_te", "baseline_stateful_fuzz", "baseline_zippy", "baseline_source_por"],
               "ablation_map": {"ablate_no_suffix": {"rqs": ["RQ2"], "targets": ["pg_ivm", "feldera", "risingwave"], "workloads": ["W1", "W2", "W3"]},
                                "ablate_no_guidance": {"rqs": ["RQ3"], "targets": ["pg_ivm", "feldera", "risingwave"], "workloads": ["W3"]},
                                "ablate_no_reduction": {"rqs": ["RQ3"], "targets": ["pg_ivm", "feldera", "risingwave"], "workloads": ["W3"]},
                                "ablate_random_lifecycle": {"rqs": ["RQ4"], "targets": ["pg_ivm", "feldera", "risingwave"], "workloads": ["W1"]},
                                "ablate_random_suffix": {"rqs": ["RQ2b"], "targets": ["pg_ivm", "feldera", "risingwave"], "workloads": ["W1", "W2", "W3"],
                                                         "matched_seed_of": "cutwitness_c"},
                                "ablate_deletion_matched_suffix": {"rqs": ["RQ2c"], "targets": ["pg_ivm", "feldera", "risingwave"], "workloads": ["W1", "W2", "W3"],
                                                                   "matched_seed_of": "cutwitness_c"}},
               "secondary_oracles": {"baseline_tlp": {"rqs": ["RQ1"], "checks": 300, "est_hours": 1.0}},
               "deterministic_suites": {"pg_ivm": {"applicable": True, "est_hours": 1.0},
                                        "risingwave": {"applicable": False, "reason": "pinned release image ships no sqllogictest runner or e2e suite"},
                                        "feldera": {"applicable": False, "reason": "pinned pipeline-manager image ships no SQL test runner"}},
               "minimization": {"est_hours_per_target": 4.0, "rqs": ["RQ5"]}}
GATE = {"max_campaign_days": 45, "reserve_vcpus": 2, "reserve_ram_gib": 8, "per_slot_disk_gib": 100, "port_span": 2000,
        "overhead_hours": 2.0, "est_hours_per_execution": 0.0003, "expected_witnesses_upper_bound": 500, "est_bytes_per_unit": 2000000}
COMMON["matrix"] = MATRIX_SPEC
COMMON["analysis_spec"] = {"version": "7", "path": "science/ANALYSIS_SPEC_v7.md", "sha256": h("science/ANALYSIS_SPEC_v7.md"),
    "ablation_families": {"ablate_no_suffix": {"rq": "RQ2", "primary_metric": "none", "inferential": False, "descriptive": "root-cause overlap and suffix-specific latent roots (post-run adjudication)"},
                          "ablate_no_guidance": {"rq": "RQ3", "primary_metric": "candidate_ttf"},
                          "ablate_no_reduction": {"rq": "RQ3", "primary_metric": "candidate_ttf"},
                          "ablate_random_lifecycle": {"rq": "RQ4", "primary_metric": "lifecycle_rate_per_1000"},
                          "ablate_random_suffix": {"rq": "RQ2b", "primary_metric": "matched_pair_exact_sign_test", "inferential": True, "paired": True},
                          "ablate_deletion_matched_suffix": {"rq": "RQ2c", "primary_metric": "matched_pair_exact_sign_test", "inferential": True, "paired": True}}}
EVID = {"adjudication_protocol": {"path": "ROOT_CAUSE_ADJUDICATION_PROTOCOL_v4.md", "sha256": h("ROOT_CAUSE_ADJUDICATION_PROTOCOL_v4.md")},
        "e3_amendment": {"path": "E3_ATTRIBUTION_AMENDMENT.md", "sha256": h("E3_ATTRIBUTION_AMENDMENT.md")},
        "rho_instrumentation_amendment": {"path": "EQUIVALENCE_SAMPLING_INSTRUMENTATION_AMENDMENT_v1.md", "sha256": h("EQUIVALENCE_SAMPLING_INSTRUMENTATION_AMENDMENT_v1.md")},
        "amendment_v1_4": {"path": "SCIENTIFIC_AMENDMENT_v1_4.md", "sha256": h("SCIENTIFIC_AMENDMENT_v1_4.md")},
        "attribution_amendment": {"path": "CUTWITNESS_C_PREEXECUTION_ATTRIBUTION_AMENDMENT_v1_2.md", "sha256": h("CUTWITNESS_C_PREEXECUTION_ATTRIBUTION_AMENDMENT_v1_2.md"),
                                  "replays_per_path": "nondet_reruns"},
        "patch": "Patch-2 pre-execution evidence instrumentation (observation only)"}
COMMON["duration_gate"] = GATE
SIGNALS = {"A": 1, "B_speedup": 2.0, "B_a12": 0.71, "D_coverage_ratio": 3.0}
real = dict(COMMON, mode="SEALED_CAMPAIGN", evidence=dict(EVID, timing_mode="wallclock"), release_state="SEALED",
            targets={
                "pg_ivm": {"kind": "real", "version": {"server_version_num": "170010", "pg_ivm": "1.16"}, "image": "build:server/targets/pgivm",
                           "container": "cw-pgivm", "container_port": 5432, "memory_gb": 32,
                           "command": ["postgres", "-c", "shared_preload_libraries=pg_ivm", "-c", "max_connections=200"], "env": {"POSTGRES_PASSWORD": "cw"},
                           "adapter_env": {"dsn_template": "host=127.0.0.1 port={port} user=postgres password=cw dbname={db}", "admin_db": "postgres",
                                           "pg_ivm_version": "1.16", "container_name": "cw-pgivm"}},
                "risingwave": {"kind": "real", "version": {"version": "3.1.0"}, "image": "risingwavelabs/risingwave:v3.1.0", "container": "cw-risingwave",
                               "container_port": 4566, "memory_gb": 32, "command": ["single_node"], "env": {},
                               "adapter_env": {"dsn_template": "host=127.0.0.1 port={port} user=root dbname={db}", "admin_db": "dev",
                                               "rescale_parallelism": 4, "container_name": "cw-risingwave"}},
                "feldera": {"kind": "real", "version": {"version": "0.366.0"}, "image": "ghcr.io/feldera/pipeline-manager:0.366.0", "container": "cw-feldera",
                            "container_port": 8080, "memory_gb": 32, "command": None, "env": {},
                            "adapter_env": {"workers": 8, "storage": True, "fault_tolerance": {"model": "exactly_once"}}}},
            workloads={"W1": {"source": "mobilitydb", "sample_routes": 20, "max_versions": 60, "min_datasets": 12, "n_validation": 8, "n_test": 16, "max_txns": 40},
                       "W2": {"pairs": 20, "sf_units": 1, "max_txns": 41}, "W3": {"txns": 10}},
            pilot={"targets": ["pg_ivm", "risingwave"], "workloads": ["W1", "W3"], "tools": ["cutwitness_c", "baseline_random_clean", "baseline_random_te", "baseline_zippy"],
                   "trials": 3, "budget": {"kind": "seconds", "value": 43200}, "signals": SIGNALS},
            full={"targets": ["pg_ivm", "feldera", "risingwave"], "workloads": ["W1", "W2", "W3"], "tools": ["cutwitness_c"] + BASELINES + ABLATIONS,
                  "trials": 10, "budget": {"kind": "seconds", "value": 14400}},
            resources={"configured_max_slots": 4, "port_base": 41000, "per_trial_cpus": 8, "per_trial_ram_gb": 32},
            server_requirements={"disk_gb": 500, "ram_gb": 136, "cpus": 34},
            tester_conformance={"correct_histories": 10000, "fault_histories": 40, "seeded_faults": FAULTS[1:], "seed": "cutwitness-c/S5"})
sim = dict(COMMON, mode="ENGINEERING_SIMULATION", evidence=dict(EVID, timing_mode="logical"), release_state="ENGINEERING",
           targets={t: {"kind": "simulated", "version": dict(real["targets"][t]["version"]), "image": "none", "fault": f}
                    for t, f in (("pg_ivm", "F9_LATENT_RESIDUAL"), ("risingwave", "NONE"), ("feldera", "F2_LOST_DELETE"))},
           workloads={"W1": {"source": "fixture", "sample_routes": 20, "max_versions": 60, "min_datasets": 1, "n_validation": 1, "n_test": 1, "max_txns": 8},
                      "W2": {"pairs": 2, "sf_units": 1, "max_txns": 5}, "W3": {"txns": 6}},
           pilot=dict(real["pilot"], trials=1, budget={"kind": "executions", "value": 3}),
           full=dict(real["full"], trials=1, budget={"kind": "executions", "value": 3}),
           resources={"configured_max_slots": 1, "port_base": 41000, "per_trial_cpus": 1, "per_trial_ram_gb": 1},
           duration_gate=dict(GATE, reserve_vcpus=0, reserve_ram_gib=0, per_slot_disk_gib=1),
           server_requirements={"disk_gb": 1, "ram_gb": 1, "cpus": 1},
           witness_closure={"min_budget": 60},
           tester_conformance={"correct_histories": 25, "fault_histories": 6, "seeded_faults": FAULTS[1:], "seed": "cutwitness-c/S5-sim"})
crash = dict(sim, targets={"pg_ivm": sim["targets"]["pg_ivm"]},
             workloads={"W3": {"txns": 5}}, capability_matrix={"pg_ivm": MATRIX["pg_ivm"]},
             pilot=dict(sim["pilot"], targets=["pg_ivm"], workloads=["W3"], tools=["cutwitness_c", "baseline_random_clean"], budget={"kind": "executions", "value": 6}),
             full=dict(sim["full"], targets=["pg_ivm"], workloads=["W3"], budget={"kind": "executions", "value": 2}),
             matrix=dict(MATRIX_SPEC, search_tools=["cutwitness_c", "baseline_random_clean"],
                         ablation_map={"ablate_no_suffix": {"rqs": ["RQ2"], "targets": ["pg_ivm"], "workloads": ["W3"]},
                                       "ablate_random_suffix": {"rqs": ["RQ2b"], "targets": ["pg_ivm"], "workloads": ["W3"], "matched_seed_of": "cutwitness_c"},
                                       "ablate_deletion_matched_suffix": {"rqs": ["RQ2c"], "targets": ["pg_ivm"], "workloads": ["W3"], "matched_seed_of": "cutwitness_c"}},
                         secondary_oracles={"baseline_tlp": {"rqs": ["RQ1"], "checks": 3, "est_hours": 0.0}},
                         deterministic_suites={"pg_ivm": {"applicable": True, "est_hours": 0.0}}),
             tester_conformance=dict(sim["tester_conformance"], correct_histories=5, fault_histories=1,
                                     seeded_faults=["F2_LOST_DELETE", "F9_LATENT_RESIDUAL"]),
             witness_closure={"min_budget": 20})
sim["matrix"] = dict(MATRIX_SPEC, secondary_oracles={"baseline_tlp": {"rqs": ["RQ1"], "checks": 4, "est_hours": 0.0}},
                     deterministic_suites={"pg_ivm": {"applicable": True, "est_hours": 0.0},
                                           "risingwave": MATRIX_SPEC["deterministic_suites"]["risingwave"],
                                           "feldera": MATRIX_SPEC["deterministic_suites"]["feldera"]})
for name, cfg in (("FROZEN_CAMPAIGN.yaml", real), ("ENGINEERING_SIMULATION.yaml", sim), ("CRASHTEST_SIMULATION.yaml", crash)):
    d = validate(cfg)
    open(os.path.join(ROOT, "campaign", name), "w").write(canonical_text(cfg))
    print(name, d)
