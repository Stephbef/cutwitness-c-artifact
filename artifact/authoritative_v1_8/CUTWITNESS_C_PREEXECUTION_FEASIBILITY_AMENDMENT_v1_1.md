# CutWitness-C — Pre-Execution Feasibility Amendment v1.1

Status: issued before any real-target execution. No real TEST (or VALIDATION) observation exists.
Pre-amendment source commit: `a859cc3`. Pre-amendment configuration digest: `36e24c592a173a1f26a492b782f744b2a8ac3afbb3ff0bf5fbd90e24b2c19ba6`.
Post-amendment commit, configuration digest and this file's SHA-256 are recorded in `science/AMENDMENT_v1_1_RECORD.json` (written after this file is frozen, so the record can hash it).

## 1. Original frozen setting (v1.0)
- 10 repetitions per stochastic search configuration.
- 24-hour wall-clock budget per full-campaign trial; 12-hour pilot trials.
- Every full-campaign tool (CutWitness-C, six baselines, four ablations) run as a 10 × 24 h trial on every target × workload.
- Zero-bug trials retained and right-censored. Pilot signals A–D and thresholds as frozen.

Projected v1.0 duration: (48 pilot units × 12 h) + (11 tools × 3 targets × 3 workloads × 10 × 24 h) = 24,336 slot-hours, about 253 days on 4 slots. Operationally infeasible before any observation.

## 2. Amended setting (v1.1)
1. **Stochastic repetitions stay at 10.**
2. **Full-campaign stochastic search-trial budget: 24 h → 4 h.** Pilot trial budget (12 h), pilot tools, targets, workloads, repetitions and thresholds are unchanged.
3. **Every unit carries exactly one execution-unit class:** `SEARCH_TRIAL`, `DETERMINISTIC_SUITE`, `MINIMIZATION`, `SECONDARY_ORACLE`, `ABLATION`, `NOT_APPLICABLE`.
4. **Classification of the existing families (no family removed):**
   - CutWitness-C, random updates + clean rebuild, random terminal-equivalent mutation, generic stateful fuzzing, Zippy-style, source-level POR → `SEARCH_TRIAL`, 10 × 4 h on every target × workload.
   - Target-native suites (B5) → `DETERMINISTIC_SUITE`, run once per target. Where the pinned release image ships no runnable native suite (RisingWave, Feldera) the unit is recorded `NOT_APPLICABLE` with the reason, never PASS.
   - ddmin (B8) and the CutWitness-C minimizer → `MINIMIZATION`, one unit per target, applied to the same S8 witnesses; not an independent search campaign.
   - Query-side metamorphic testing (TLP, B7) → `SECONDARY_ORACLE`: a fixed, seeded set of 300 checks per target × workload on the batch query path. It is an oracle on a different execution path, not a time-to-first-divergence search, so it contributes to RQ1 only and is excluded from RQ3 time comparisons.
   - Ablations → `ABLATION`, 10 × 4 h, mapped to the RQ they inform:
     - no characterization suffixes → RQ2, all targets × W1, W2, W3;
     - no automaton guidance → RQ3, all targets × W3;
     - no ≡_K reduction → RQ3, all targets × W3;
     - random lifecycle placement → RQ4, all targets × W1.
5. **Mandatory duration/resource preflight** with `max_campaign_days = 45`, slots derived from measured resources (CPU, RAM, disk, ports, configured maximum) with explicit host reserve. Above 45 days the campaign is BLOCKED; no bypass flag exists. Exceeding the limit requires a new versioned amendment.

## 3. Scientific rationale
This is a prospective feasibility correction only, made before any real observation. It does **not** claim that a 4-hour trial has the statistical power of a 24-hour trial: effects requiring more than 4 hours of search will be censored more often, and conclusions are scoped to a 4-hour budget. Every removed `10 × 24 h` multiplication is either a budget change applied symmetrically to all search tools, or a reclassification of an operation that is not a stochastic search (native suites, minimization of fixed witnesses, a fixed-check secondary oracle), or an ablation restricted to the research question it answers.

## 4. Preserved without change
Number of stochastic repetitions (10); all tool and baseline families; pilot logic, tools, budgets and thresholds (A ≥ 1 candidate; B ≥ 2× with A12 ≥ 0.71 on every pilot target; C; D ≥ 3× coverage); target set; workload set; seeds and the HMAC derivation rule; RQ1–RQ5; bug-accounting protocol; right-censoring of zero-bug runs; VALIDATION/TEST firewall; UPGRADE excluded on all targets.

## 5. Exact diff of affected parameters
| Parameter | v1.0 | v1.1 |
| --- | --- | --- |
| full.budget | 86,400 s | 14,400 s |
| unit classes | none (all trials) | six classes, per Section 2.4 |
| B5 native suites | 10 × 24 h per target × workload | 1 `DETERMINISTIC_SUITE` per target (or `NOT_APPLICABLE`) |
| B7 TLP | 10 × 24 h per target × workload | 1 `SECONDARY_ORACLE` (300 seeded checks) per target × workload |
| B8 ddmin | listed baseline | 1 `MINIMIZATION` per target on S8 witnesses |
| ablations | 10 × 24 h on all 9 target × workload cells | 10 × 4 h on the cells mapped above |
| duration gate | none | 45 days, measured slots, fail closed |
