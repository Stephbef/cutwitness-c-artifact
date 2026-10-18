# Baseline Fidelity Report (Amendment v1.4)

Every stochastic arm receives the same per-cell budget (10 repetitions × 4 h), a cell-specific HMAC seed, the same targets and capability matrix (UPGRADE excluded; top-k views excluded on pg_ivm), and the same oracles and triage. The re-implemented testers implement the **public mechanism** named below. They are not reproductions of proprietary systems.

| Arm | Behavioral contract | Action-generation policy | Validation frequency | Lifecycle handling | Unit class |
|---|---|---|---|---|---|
| random-clean (Enzyme-style) | incremental vs complete over random changes | fresh random legal histories (W generator) | clean-rebuild comparison after every history | none | SEARCH_TRIAL |
| random terminal-equivalent | path vs path over equivalent histories | random reorder, split, coalesce, insert-then-revert and revert-and-reapply detours | after every history (O1 + O2) | random placement | SEARCH_TRIAL |
| stateful fuzzing | long statement sequences | bursts of DML with random lifecycle (statement-sequence fuzzer style) | after every sequence | random | SEARCH_TRIAL |
| Zippy-style | Materialize Zippy's public mechanism: random insert/delete ranges, restarts, validation after each action | action model with expected state from the reference | after every action | restarts and supported kinds | SEARCH_TRIAL |
| source-level POR | prune by row/key independence at the source | random mutations with source-fingerprint pruning (ρ-sampled) | after every history | random | SEARCH_TRIAL |
| TLP (secondary oracle) | query partitioning on the batch query path | 300 seeded checks per cell, type-aware predicate | per check | n/a | SECONDARY_ORACLE (no primary roots) |
| matched random suffix (control) | identical to CutWitness-C except the suffix rule | random legal same-key continuation of length \|c_ref\| (RANDOM_SUFFIX_MATCHING_CONTRACT.md) | O4 after every suffix step | as CutWitness-C | ABLATION (RQ2b) |

## Seeded-fault sanity checks (ENGINEERING VALIDATION ONLY — NOT SCIENTIFIC RESULTS)
Toy reference engine with one seeded fault, W3 generator, 6 trials per cell, 10-execution logical budget (`qa/BASELINE_SANITY.json`). The number shown is trials with a reproducible candidate.

| Arm | F1 wrong multiplicity | F2 lost delete | F4 MIN/MAX extremum | F8 lifecycle restore | F9 latent residual |
|---|---|---|---|---|---|
| `cutwitness_c` | 6/6 | 6/6 | 1/6 | 6/6 | 6/6 |
| `baseline_random_clean` | 6/6 | 6/6 | 3/6 | 0/6 | 6/6 |
| `baseline_random_te` | 3/6 | 3/6 | 0/6 | 6/6 | 6/6 |
| `baseline_stateful_fuzz` | 6/6 | 6/6 | 4/6 | 5/6 | 5/6 |
| `baseline_zippy` | 6/6 | 6/6 | 3/6 | 6/6 | 5/6 |
| `baseline_source_por` | 3/6 | 3/6 | 0/6 | 5/6 | 6/6 |
| `ablate_random_suffix` | 6/6 | 6/6 | 3/6 | 6/6 | 6/6 |
| `ablate_no_suffix` | 6/6 | 5/6 | 1/6 | 6/6 | 6/6 |

**Reading.**
- Every baseline detects several seeded faults, so none is a strawman.
- Baselines without lifecycle events (random-clean) miss the lifecycle fault, as designed.
- On F4 at this tiny budget, CutWitness-C detects fewer trials (1/6) than stateful fuzzing (4/6), the matched random suffix (3/6) and random-clean (3/6). This is an adverse engineering signal, recorded here and not tuned away. The real campaign, at full budgets on real targets, decides the scientific question (RQ2b decision rules, SCIENTIFIC_AMENDMENT_v1_4.md).
