# Baseline Fidelity (Amendment v1.1 classes)

| Family | Source mechanism | Implementation | Deviation | Unit class |
| --- | --- | --- | --- | --- |
| B1 random updates + clean rebuild | Enzyme RQG testing (Sec. 5) | `baseline_random_clean` | W3 generator instead of Enzyme's RQG | SEARCH_TRIAL |
| B2 random terminal-equivalent mutation | Freeze | `baseline_random_te` | — | SEARCH_TRIAL |
| B3 generic stateful SQL fuzzing | sqlsmith-style statement sequences | `baseline_stateful_fuzz` (bursts of DML + random lifecycle, no guidance) | no SQL-text grammar fuzzing; DML sequences only | SEARCH_TRIAL |
| B4 Zippy-style | Materialize Zippy (watermark expected-state model) | `baseline_zippy` (insert/delete ranges, restarts, validation after every action) | expected state from the reference model, which is stronger than watermarks | SEARCH_TRIAL |
| B5 target-native suites | pg_ivm `make installcheck` | `b5_run_native` | RisingWave and Feldera release images ship no runnable suite | DETERMINISTIC_SUITE (pg_ivm); NOT_APPLICABLE (RisingWave, Feldera) |
| B6 source-level POR | DPOR with row/primary-key independence | `baseline_source_por` | — | SEARCH_TRIAL |
| B7 query-side metamorphic (TLP) | SQLancer TLP | `b7_tlp` on the batch query path, type-aware predicate | fixed 300 seeded checks per target × workload | SECONDARY_ORACLE |
| B8 ddmin | Zeller & Hildebrandt | `baselines.ddmin` on the same S8 witnesses | — | MINIMIZATION |
| Ablations: no suffix / no guidance / no reduction / random lifecycle | Freeze | `ablate_*` | mapped to RQ2 / RQ3 / RQ3 / RQ4 cells (Amendment v1.1) | ABLATION |

No family was removed; non-search operations are not multiplied as 10 × 4 h trials.
