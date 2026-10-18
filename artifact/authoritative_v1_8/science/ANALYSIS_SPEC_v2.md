# Analysis Specification v2 (pre-registered before any real execution; Patch-2)

Unchanged from v1: primary comparisons CutWitness-C vs each of the five SEARCH_TRIAL baselines, per target, workloads pooled;
unit = trial; A12 = P(baseline time > CutWitness-C time); two-sided Mann–Whitney U (asymptotic, continuity- and tie-corrected);
Holm within each target's five-comparison family; Kaplan–Meier and log-rank on time to first candidate, right-censored at budget.

## Added metrics (definitions frozen)
- **Histories executed**: histories actually run against the target by the search loop (`category = search` or `path_pair`,
  `executed = true`). Generated-but-pruned (`PRUNED_EQUIVALENT`) and generated-but-unselected (`NOT_SELECTED`) candidates are
  recorded with `executed = false` and never counted. Triage, minimization and closure re-executions are separate categories.
- **Latent-only time to first divergence**: time (search clock: executions in logical mode, seconds in wall-clock mode) of the first
  candidate (triage class 7/8, reproduced) divergence whose cut observation agreed with the reference and which diverged during the
  characterization suffix (FC holds, CC fails). Right-censored at budget. Never replaced by overall time to first divergence.
- **Lifecycle denominators**: lifecycle events contained in executed search histories, with type, position, placement
  (semantic | semantic_fallback_random | random | generator | inherited) and support (only supported kinds are generated;
  UPGRADE is excluded). RQ4 rate = reproducible lifecycle-class candidates / executed lifecycle events × 1000.
- **Minimizer calls**: `predicate_calls` = predicate evaluations that executed the target; `predicate_calls_logical` additionally
  counts evaluations rejected by the legality check before execution. Neither minimizer caches results.

## Ablation families (primary, Holm within each family across its mapped targets; unit = trial; workloads pooled within the mapped cells)
| Family | RQ | Primary metric | A12 direction | Tests |
|---|---|---|---|---|
| ablate_no_suffix | RQ2 | latent-only time to first divergence | P(ablation time > CutWitness-C time) | MW, log-rank, KM figure |
| ablate_no_guidance | RQ3 | time to first candidate | P(ablation time > CutWitness-C time) | MW, log-rank |
| ablate_no_reduction | RQ3 | time to first candidate | P(ablation time > CutWitness-C time) | MW, log-rank |
| ablate_random_lifecycle | RQ4 | lifecycle rate per 1,000 executed lifecycle events (per trial) | P(CutWitness-C rate > ablation rate) | MW |

**Descriptive only (no test, no multiplicity):** coverage and histories executed for every method (RQ3 coverage-vs-executions);
latent and lifecycle counts; minimizer lengths, calls and replay (RQ5); TLP secondary-oracle discrepancies; native suite status.
