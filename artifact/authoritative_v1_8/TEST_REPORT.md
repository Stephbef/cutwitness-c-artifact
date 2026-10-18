# TEST REPORT (generated from the packaged `qa/junit.xml`)

> **V1.8 pre-execution amendment** (`PREEXECUTION_AMENDMENT_V1_8_DELETION_MATCHED_CONTROL.md`). It adds the deletion-matched control: RQ2c, a new arm of 90 units.
> The campaign becomes 963 units and 4,200 slot-hours (43.75 days at 4 slots), with analysis spec v7 and 318 tests passing.
> Figures below that say 873 units, 3,840 slot-hours, 40 days or 307 tests refer to V1.7.2 and are superseded.


Source tree: commit `7c81b10710c9ea54c1b260b4780233a0c6620ed4`, active-source digest `9bd7bf1fbb5836ccec4ad135d014a1c29dd3761084c8171b2bdd7316ee81fc60`; `qa/junit.xml` SHA-256 `7005637f8d7f7278928c1226d132fc6cbb18a1f019a66b25a85ee4bcebf7d60a`.

**Total 307 · passed 307 · failed 0 · errors 0 · skipped 0.**

| Suite | Tests |
| --- | ---: |
| `test_adapters` | 15 |
| `test_analysis` | 9 |
| `test_attribution` | 7 |
| `test_campaign` | 9 |
| `test_config_consistency` | 3 |
| `test_core` | 9 |
| `test_crash_matrix` | 9 |
| `test_e3_attribution` | 18 |
| `test_evidence_plumbing` | 13 |
| `test_nondeterminism` | 52 |
| `test_packaging` | 4 |
| `test_pilot` | 12 |
| `test_preflight_matrix` | 5 |
| `test_random_suffix` | 15 |
| `test_regressions` | 6 |
| `test_release_docs` | 3 |
| `test_rho_instrumentation` | 20 |
| `test_rq2_semantics` | 44 |
| `test_rq2b_paired` | 8 |
| `test_security` | 4 |
| `test_theory` | 11 |
| `test_workloads` | 31 |

## Additional evidence (ENGINEERING VALIDATION ONLY — local, not a real-server run)
- **Crash/resume:** 9/9.
- **Simulation:** `COMPLETE_FULL_CAMPAIGN`, results digest `85f93c25de75076b` (identical to V1.7).
- **Zero search semantics vs V1.7 and V1.6:** HOLDS (`qa/RHO_ZERO_SEARCH_SEMANTICS_PROOF.json`). The ρ records are also identical to V1.7 in this simulation.
