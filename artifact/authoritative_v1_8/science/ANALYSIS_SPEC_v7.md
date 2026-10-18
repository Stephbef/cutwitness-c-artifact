# Analysis Specification v6 (pre-registered before any real execution; v5 + analysis-only amendment v1.5)

> **EFFECTIVE RQ2b SPECIFICATION (authoritative; v1.5).**
> - RQ2b inference: matched exact two-sided sign test per target, with a Clopper–Pearson 95% interval and Holm across the valid target-level tests.
> - KM curves: descriptive only.
> - For RQ2b there is **no Mann–Whitney, no A12 and no log-rank**.
> - Any RQ2b statistics text below marked HISTORICAL is superseded and must not be used.
> - `matrix.*` in the frozen campaign is the authoritative execution specification.

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
| ablate_random_suffix | RQ2b | **matched pairs (v6)**: exact two-sided sign test on matched win/loss | — | exact sign test; Holm over the valid target-level tests; KM descriptive only |
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

## Amendment v1.4 — RQ2 as two layers
**RQ2a, existence and attribution.** Co-primary, descriptive, no tests on root-cause counts. Adjudication protocol v3 supplies:
- continuation-latent roots;
- HISTORY_CONDITIONED_LATENT, CONTINUATION_TRIGGERED and UNRESOLVED_ATTRIBUTION roots;
- roots also found by the no-suffix ablation;
- suffix-stage-specific roots (full vs no-suffix).

**RQ2b, mechanism isolation.** Inferential family `ablate_random_suffix`:
- Endpoint: CutWitness-C vs the matched random suffix on latent-only time to first reproducible divergence, per target, workloads pooled within the mapped cells, trial unit, right-censored at the budget. Both arms execute suffixes, so the endpoint is applicable to both.
- **HISTORICAL — SUPERSEDED BY AMENDMENT v1.5 BELOW — MUST NOT BE USED FOR SCIENTIFIC ANALYSIS:** ~~Statistics: A12 = P(random-suffix time > CutWitness-C time); two-sided Mann–Whitney; KM; log-rank; Holm over the three target-level comparisons.~~
- Root-level, descriptive:
  - latent roots found by each arm;
  - overlap;
  - full-only (**characterization-specific**);
  - random-only;
  - the history-conditioned split.

**Terminology (never conflated).**
- **suffix-stage-specific:** full vs no-suffix.
- **characterization-specific:** found under reference-derived suffixes but not under matched random suffixes at equal budget.
- **CW-exclusive:** vs the five search baselines.
- **baseline-exclusive:** found only by search baselines.

**Families are disjoint.** Holm is applied within each pre-registered family:
- search baselines (per target, 5);
- guidance, across targets;
- reduction, across targets;
- placement, across targets;
- random suffix, across targets.

There is no global correction across unrelated questions. The suffix-stage (no-suffix) comparison remains descriptive.

**Decision rules:** SCIENTIFIC_AMENDMENT_v1_4.md.

## Amendment v1.5 (analysis only; supersedes ONLY the RQ2b inferential paragraph of v5)
Amendment v1.5 is an analysis-only pre-execution correction. Amendment v1.4 deliberately made `cutwitness_c` and `ablate_random_suffix` a
**matched-pair** experiment: shared trial seed, pre-suffix search, candidate stream, exposed key, opportunity and requested suffix length.
Observations across the arms are therefore paired, and the unpaired v5 tests (Mann–Whitney, A12, log-rank) do not fit. No treatment
changed and no data existed when this was corrected. The shared seeds are kept.

**Pairs.**
- Per target, one pair per workload × repetition in the control's mapped cells: 3 × 10 = 30 per target in the frozen matrix.
- Each arm contributes T, latent-only time to first reproducible divergence truncated at the common budget, and δ, 1 if observed and 0 if right-censored.
- **Integrity:** exactly one unit of each arm per cell and repetition, with the same seed, budget, applicability, workload, target and repetition. Otherwise `RQ2B_ANALYSIS_BLOCKED`, with no unpaired fallback.

**Pair outcome.**
- **CW_WIN:** δ_CW = 1 and (δ_RS = 0 or T_CW < T_RS).
- **RANDOM_WIN:** δ_RS = 1 and (δ_CW = 0 or T_RS < T_CW).
- **TIE:** both censored, or observed at exactly the same recorded search time. No arbitrary winner is assigned.

**Primary inference.**
- Per target: W = CW_WIN, L = RANDOM_WIN, N = W + L. Test H0: P(CW_WIN | non-tie) = 0.5 with an exact two-sided binomial sign test.
- Report W, L, ties, N, W/N, an exact Clopper–Pearson 95% interval and the exact p-value.
- If N = 0, the p-value is N/A ("no informative discordant matched pairs").
- **Multiplicity:** Holm over the valid target-level p-values (at most three), with the reduced family size reported.

**Removed for RQ2b only:** Mann–Whitney, A12 and log-rank as inferential outputs. They remain unchanged for the independently seeded families (search baselines, guidance, reduction, placement).

**Descriptive only.**
- KM curves, labelled "descriptive matched-arm survival curves".
- Median T_CW and median T_RS among observed events.
- Median paired difference among pairs where both arms observe events.
- No paired parametric test.

**Outputs.** `rq2b_matched_pairs.csv`, `rq2b_matched_summary.csv`, `rq2b_matched_timing.csv`.

**Root-level RQ2b comparisons** (characterization-specific, overlap, random-only, history-conditioned split) remain descriptive and post-adjudication. The v1.4 decision rules are unchanged.

## v7 (pre-execution amendment V1.8): RQ2c — deletion-matched continuation control

**Question.** Does the directed verification continuation outperform a random legal continuation that matches it in key, length and number of delete steps? The question is about order and content beyond deletion composition.

**Arm.** `ablate_deletion_matched_suffix` runs the same 90 cells as `ablate_random_suffix`: 3 targets × W1, W2, W3 × 10 repetitions. Each unit uses the matched `cutwitness_c` seed and a 4-hour budget.

**Per opportunity.**
- The directed continuation is synthesized as usual, but not executed.
- A continuation with the same key, the same length and the same count of delete steps is executed in its place, with the delete positions drawn uniformly.
- Deletes are uniform over the key's row copies, with legal foreign-key cascades. Inserts follow the frozen random-insert rule.
- Every prefix is legal. An infeasible order is resampled at most 16 times; if all fail, the opportunity has no continuation (fail closed).
- The RNG stream is domain-separated (`deletion-matched|seed|exec`), so the search stream, and with it the candidate stream, is identical to `cutwitness_c`.

**Endpoint and test.** Identical to RQ2b:
- endpoint: the first latent candidate, censored at the 4-hour budget;
- outcome: CW_WIN / RANDOM_WIN / TIE via `pair_outcome`;
- test: exact two-sided sign test on the informative pairs, with a Clopper–Pearson interval.

**Multiplicity.** RQ2c is its own primary family with Holm correction across the 3 targets. It does not alter the RQ2b family.

**Root level.** A root is order-specific if `cutwitness_c` finds it and the deletion-matched arm does not; this is adjudicated blind, as for characterization-specific roots.

**Outputs.**
- `rq2c_matched_pairs.csv`
- `rq2c_matched_summary.csv`
- `rq2c_matched_timing.csv`

**Interpretation.** RQ2b separates content from extra updates. RQ2c separates order and content from deletion composition.
