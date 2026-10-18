# Release Hygiene v1.5.1 — current-state document audit

No treatment, analysis, seed, matrix cell, statistical method, hypothesis or manuscript claim changed.

| Occurrence | File | Classification | Action |
|---|---|---|---|
| 36.25-day / 48.3-day duration arithmetic | README_FIRST.md | ACTIVE_STALE | replaced: 3,840 slot-h; 4 measured slots 960 h = 40.0 days PASS; 3 slots 1,280 h = 53.33 days BLOCKED; slots must be measured by S2 |
| "four ablations" (overview) | IMPLEMENTATION_CLOSURE_REPORT.md | ACTIVE_STALE | replaced with "five ablations", naming `ablate_random_suffix` as the RQ2b control |
| "the four ablations" (docstring) | cutwitness/baselines.py | ACTIVE_STALE | docstring only (behavior-neutral) |
| `ablations`, `full.tools` without `ablate_random_suffix` | campaign/*.yaml via tools/make_config.py | ACTIVE_STALE | synchronized (option B); documented as non-authoritative mirrors, since execution reads `matrix.*` and `pilot.tools` only; guarded by tests/test_config_consistency.py |
| v1.4 RQ2b paragraph prescribing A12 / MW / log-rank | science/ANALYSIS_SPEC_v6.md | ACTIVE_STALE (unmarked historical text) | marked HISTORICAL — SUPERSEDED BY AMENDMENT v1.5 BELOW — MUST NOT BE USED FOR SCIENTIFIC ANALYSIS; effective RQ2b block added at the top. No v7 created |
| "four ablations" | CUTWITNESS_C_PREEXECUTION_FEASIBILITY_AMENDMENT_v1_1.md (root and science/) | HISTORICAL_PROVENANCE | unchanged |
| RQ2b MW / A12 / log-rank | science/ANALYSIS_SPEC_v5.md | HISTORICAL_PROVENANCE | unchanged (superseded by v6) |
| "Removed for RQ2b only: MW, A12, log-rank" | science/ANALYSIS_SPEC_v6.md | CORRECT_CURRENT | unchanged |
| "RQ2b has no Mann–Whitney, A12 or log-rank output" | IMPLEMENTATION_CLOSURE_REPORT.md | CORRECT_CURRENT | unchanged |
| 783 / 3,480 | — | none found in current files | — |
