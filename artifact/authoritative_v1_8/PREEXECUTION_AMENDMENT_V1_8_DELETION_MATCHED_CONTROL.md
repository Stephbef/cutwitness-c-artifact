# Pre-execution amendment V1.8: deletion-matched continuation control (RQ2c)

**Status.** Pre-execution. V1.7.2 is superseded for execution by V1.8, and the V1.7.2 package remains archived unchanged.

**No real result precedes this amendment.**
- No sealed observed-results bundle or `FINAL_VERDICT.json` exists in any package or in the anonymous repository; its status file reports `observed_result_bundle_present: false`.
- The only executions so far are engineering simulations on the toy reference engine.

## Rationale

An external simulated SIGMOD review (AE decision: revision) raised one objection to the content claim. The V1.7.2 matched random continuation equalizes key, length and opportunity, but not deletion composition: it inserts with probability 0.5 whenever the key has rows. A directed drain could therefore win simply because it deletes more.

## Changed scientific question

RQ2b is unchanged: does the directed continuation beat a random legal continuation of the same length on the same key?

RQ2c is new: does it also beat a random legal continuation with the same key, the same length and the same number of delete steps? RQ2c separates order and content from deletion composition.

## Arm

`ablate_deletion_matched_suffix`. For each opportunity:
- The directed continuation is synthesized but not executed.
- A continuation with the same key, the same length and exactly as many delete steps is executed in its place. The delete positions are drawn uniformly; deletes pick a uniform same-key row copy, with legal foreign-key cascades; inserts follow the frozen random-insert rule.
- Every prefix is legal. An infeasible order is resampled at most 16 times; if all fail, the opportunity has no continuation (fail closed).

Shared with the other arms: guidance, reduction, lifecycle placement, O4 cadence, budget and seed are identical to `cutwitness_c`.

## RNG contract

The arm draws from a domain-separated stream, `sha256("deletion-matched|seed|exec")`. The search RNG is untouched, so the executed candidate histories are identical to those of `cutwitness_c` and `ablate_random_suffix`; this is tested.

## Matrix and feasibility

| | V1.7.2 | V1.8 |
|---|---:|---:|
| Units | 873 | 963 |
| Ablation units | 270 | 360 |
| New arm | — | 90 (3 targets × 3 workloads × 10 repetitions, the same cells as RQ2b) |
| Search slot-hours | 3,816 | 4,176 |
| Non-search slot-hours | 24 | 24 |
| Total slot-hours | 3,840 | 4,200 |
| Duration at 4 effective slots | 40.0 days | 43.75 days |

Feasibility against the 45-day cap:
- The cap allows 4 × 45 × 24 = 4,320 slot-hours, and V1.8 needs 4,200.
- With 3 slots the duration gate still returns BLOCKED, so the gate rule is unchanged.

The pilot and signals A–D are unchanged, because the pilot contains no ablation units.

## Analysis (spec v7)

- **RQ2c family.** Endpoint, pair outcome, exact sign test and Clopper–Pearson interval are identical to RQ2b. RQ2c is a separate primary family with Holm correction across the 3 targets; the RQ2b family is untouched.
- **Order-specific roots.** A root is order-specific if `cutwitness_c` finds it and the deletion-matched arm does not. This is adjudicated blind.

## Interpretation fixed before execution

- If directed continuations beat both controls, the paper may claim an effect of order and content beyond deletion composition.
- If they beat the random control but not the deletion-matched one, the content claim narrows to deletion composition.
- Roots found by the deletion-matched arm are not order-specific.

## Evidence

- **Tests.** 318 passed, 0 failed: 307 existing tests, including updated pins for totals, gate projection and spec version, plus 11 new tests in `tests/test_v18_deletion_matched.py`, among them the witness-closure order regression test.
- **Crash/resume matrix.** All points pass.
- **Zero regression for V1.7.2 arms** (`qa/V1_8_ZERO_SEARCH_SEMANTICS_PROOF.json`): 110 of 110 shared simulation units are identical, 48 of 48 witnesses are byte-identical, and target executions match (291 = 291).
- **Witness closure.** The first V1.8 build let the new arm sort first in witness closure, which changed 9 witness files, 4 of them in their stored continuation. `closure_order` keeps the V1.7.2 owner order and places post-V1.7.2 arms last, so the new arm can only create witnesses for keys no V1.7.2 arm reached. Root attribution reads per-unit results and was never affected.

## Changed files

- `cutwitness/suffix.py`, `cutwitness/pipeline.py`, `cutwitness/analysis.py`, `cutwitness/controller.py` (witness-closure order)
- `tools/make_config.py`, `tools/make_registry.py`
- `science/ANALYSIS_SPEC_v7.md`
- `campaign/*.yaml` (regenerated)
- `MANUSCRIPT_EVIDENCE_REGISTRY.csv`
- tests, QA evidence and manifests
