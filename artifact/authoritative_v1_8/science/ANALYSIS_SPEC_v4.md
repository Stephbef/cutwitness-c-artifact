# Analysis Specification v4 (pre-registered before any real execution; v3 + pre-execution analysis amendment v1.3)

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
| ablate_no_suffix | RQ2 | **none (v4: descriptive only, see below)** | — | — |
| ablate_no_guidance | RQ3 | time to first candidate | P(ablation time > CutWitness-C time) | MW, log-rank |
| ablate_no_reduction | RQ3 | time to first candidate | P(ablation time > CutWitness-C time) | MW, log-rank |
| ablate_random_lifecycle | RQ4 | lifecycle rate per 1,000 executed lifecycle events (per trial) | P(CutWitness-C rate > ablation rate) | MW |

**Descriptive only (no test, no multiplicity):** coverage and histories executed for every method (RQ3 coverage-vs-executions);
latent and lifecycle counts; minimizer lengths, calls and replay (RQ5); TLP secondary-oracle discrepancies; native suite status.

## Latent attribution (Amendment v1.2; descriptive only)
`latent_attribution.csv`: one row per reproducible latent witness with E1 (history path) and E2 (fresh load of src(h)) results and
the class HISTORY_CONDITIONED_LATENT / CONTINUATION_TRIGGERED / UNRESOLVED_ATTRIBUTION. Counts are reported per target, at witness
and (after adjudication, protocol v2 Section J) root-cause level. No test and no multiplicity correction is applied.

## Amendment v1.3 (analysis interpretation only; found before any data)
A latent witness requires FC(h) and a divergence during an **executed** characterization suffix. `ablate_no_suffix` and the five search
baselines execute no suffix (`suffix=False`), so they cannot emit a latent witness or a latent-only time to first divergence **by
construction**. Comparing that endpoint across such arms would turn a structural capability difference into a p-value.
- **Removed:** the inferential `ablate_no_suffix` family (latent-only time to first divergence; A12, Mann-Whitney, log-rank, Holm) and the
  full-versus-no-suffix latent survival comparison. Without p-values, the no-suffix comparison receives no test.
- **Witness level:** latent witness counts and latent-only times are reported only for arms that execute a suffix; for the others every
  latent field is `N/A - arm executes no characterization suffix` (never an observed zero). `latent_ttf_event.csv` carries
  `latent_endpoint = APPLICABLE | NOT_APPLICABLE_BY_DESIGN`; `fig_latent_survival_<target>.svg` shows CutWitness-C only, descriptively.
- **RQ2 evidence (descriptive, from the adjudication ledger and `latent_attribution.csv`):** continuation-latent root causes found by full
  CutWitness-C; how many of them the no-suffix arm also discovered through another manifestation (root-cause overlap, never a no-suffix
  latent event); suffix-specific latent root causes; the full-arm latent witness count; the full-arm latent-only time distribution;
  history-conditioned / continuation-triggered / unresolved attribution.
- **Scope of the conclusion:** the no-suffix ablation shows whether adding the characterization-suffix stage changes root-cause discovery at
  equal budgets. It does not show that specification-derived suffixes outperform random continuations of equal length; no such claim is made.
- **Pilot signal C** (frozen, unchanged): because no baseline executes a suffix, its latent branch reflects a capability difference and is
  never reported as comparative evidence.
Unchanged: search, candidate generation, target execution, units, seeds, budgets, treatment, target versions, pilot rules, and the
guidance, reduction and placement families.
