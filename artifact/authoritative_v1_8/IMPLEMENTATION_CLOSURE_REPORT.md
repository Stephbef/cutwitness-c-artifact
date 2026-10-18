# IMPLEMENTATION CLOSURE REPORT

## Verdict
**BLOCKED — real-target conformance not yet executed.** All locally executable gates pass. Live conformance of pg_ivm, Feldera and RisingWave
requires a container runtime; it is S4 of the sealed campaign and fails closed. Mock or simulated evidence can never satisfy it.

## Amendment v1.1
Path `CUTWITNESS_C_PREEXECUTION_FEASIBILITY_AMENDMENT_v1_1.md` (identical copy in `science/`), SHA-256 `a44f721ca7252cde7d1f1d33608c802d54d15864c67b7b0e3ffc976f10c1c535`.
Pre-amendment commit `a859cc33189e002714c00a22b7540e88333c6757`, config digest `36e24c592a173a1f26a492b782f744b2a8ac3afbb3ff0bf5fbd90e24b2c19ba6`.
Post-amendment commit `ab065a9b9aa6a19d4592d6e4a37ead5d94b29455`, config digest `b50e41b8f905fd1bd60118a7e5245f9414aaf6fcd45483a7d95e76fa6262cad5`.
Packaged config digest `a4b2fc7ca015c099aa348e57041cc7e7a83b55a134f31d615108f91f6d2ea1b1`; scientific parameter changes after the amendment: none.
Changed: full search-trial budget 86,400 s → 14,400 s; six execution-unit classes; B5 → DETERMINISTIC_SUITE / NOT_APPLICABLE; B7 → SECONDARY_ORACLE;
B8 → MINIMIZATION; ablations mapped to RQ cells; 45-day fail-closed duration gate.

## Conformance provenance
| Evidence | Result | Counts toward real-target gate |
| --- | --- | --- |
| Protocol mocks (DuckDB-backed pgwire, Feldera REST, Docker) | 90/90 | no |
| Local non-container real targets | none executed | — |
| Real targets (pg_ivm, Feldera, RisingWave) | not executed | required; server S4 |

**Earlier Feldera seed-14 event — classification `MOCK_CONFORMANCE`.** Target: Feldera protocol mock; adapter `FelderaAdapter`; view
`v_group`; differing row: engine `(3, 3, 7.0000, AVG_MISMATCH:2.3333333333333335, 1.0000)` vs reference `(3, 3, 7, 2.333333, 1)`.
Incremental read and clean rebuild agreed with each other: True; reference equalled DuckDB O3:
True; root cause: adapter parsed a binary AVG as an exact Decimal (adapter defect, not reference/DuckDB).
Fixed in `3c6430932792`; regression `test_regression_2_avg_canonicalization_and_exact_types`; seed 14 passes in the 30-seed sweep.
It never counted toward any real-target gate (`qa/CONFORMANCE_PROVENANCE.json`).

## Implemented components
Core model, reference model, transformations with proofs, ≡_K, semantic transition automata, realizer, characterization suffixes, O1–O4,
ordered triage (10-rerun nondeterminism identity including the triggering execution), slice-1-minimal minimizer, prefix-trie executor;
adapters for pg_ivm / RisingWave (pgwire) and Feldera (REST) with explicit capability refusal; per-slot deployment, readiness, exact-version
evidence, cpuset/memory isolation, cleanup; W1 (catalog client, frozen selection, firewall, licence classes, normalization, recurrence-preserving
versions, legal diffs), W2, W3; baselines B1–B8 and five ablations (the fifth, `ablate_random_suffix`, is the RQ2b mechanism-isolation control added by Amendment v1.4); S0–S12 controller with campaign matrix, 45-day gate, crash points, torn-tail
recovery, demotion rule, parent-only journaling; stdlib statistics; SVG/CSV analysis; offline wheelhouse; `run_one_shot.sh`.

## Defects found and fixed during closure (all with tests)
Conformance contract double schema creation; delete-before-insert ordering in all adapters; Feldera binary-AVG parsing (seed-14);
triage omitted the triggering execution from the nondeterminism identity; Kaplan–Meier early stop; permanent errors retried into TIMEOUT;
W1 mass-reinsert fixture was a no-op; TLP integer predicate on text columns; manifest `.gitignore` exclusion mismatch; plus earlier:
RisingWave upgrade leakage, AVG canonicalization, S5 suffix gate, dead-key probe rows, per-witness S8 resumability.

## Engineering validation (ENGINEERING VALIDATION ONLY — NOT SCIENTIFIC RESULTS)
Clean-state simulation `COMPLETE_FULL_CAMPAIGN` (digest `6cc9f1dda43103506711f84893a95103674d9526fa41c74caba37e2677e64dbb`), all executable units committed, no duplicates,
2 NOT_APPLICABLE journaled, 0 operational failures, 0 candidates on the correct simulated target, 9 TLP units committed.
Crash/resume: 9/9 digest-equal.

## Known limitations
- Real adapters' wire behaviour is verified only against mocks; S4 is the first live check.
- The pg_ivm base-image digest is not journaled separately (the built image ID is).
- W2 is TPC-H-shaped, not dbgen byte-identical; AVG equality uses declared tolerance rules for binary/decimal engine results.

## Patch-2 — pre-execution evidence instrumentation (observation only)
Classification: PRE-EXECUTION EVIDENCE-INSTRUMENTATION PATCH; no scientific amendment required (`PATCH2_RECORD.json`).
Base: analysis micro-fix (Holm per target) applied at `3b6130fd8f5e`; Patch-2 commit `103dcb0f8081`; patch digest `2eae884d497b1d9803e88d470de610b6d2902b76c7a861a744d7e270e6bedf7d`.
Producers added: histories executed (raw + summary), latent-only time to first divergence, ablation families (ANALYSIS_SPEC_v2, Holm within
family), lifecycle denominators and RQ4 rates, minimizer predicate calls (target and logical) with replay, S1 host facts, journal timestamps,
blind adjudication worksheet. Pre-registered: `ROOT_CAUSE_ADJUDICATION_PROTOCOL_v1.md` (SHA-256 `977f08a8f558ac39946fa9c42ddf769a465124c493a5ffa52c4ef680ea04113f`),
`science/ANALYSIS_SPEC_v2.md` (SHA-256 `171df8710b7f4414802757fd2118abd00eeefdcd6d158f46aab7c6892c2c36bb`), `MANUSCRIPT_EVIDENCE_REGISTRY.csv` (every manuscript number → one observed path;
per-slot CPU/RSS and TLP reproduced/confirmed counts removed from the manuscript plan for lack of a producer).
Behaviour invariance: 44/44 trial fingerprints and 8/8 campaign-unit fingerprints identical to pre-patch.

## Amendment v1.2 — latent attribution (evidence classification only)
S8 now replays every reproducible latent witness along the history path (E1) and from a fresh one-transaction load of its final cut
(E2), each 10 times, and classifies it HISTORY_CONDITIONED_LATENT, CONTINUATION_TRIGGERED or UNRESOLVED_ATTRIBUTION
(`attribution/*.json`, `latent_attribution.csv`). Adjudication protocol v2 (Section J) restricts claims of history-conditioned state
to HISTORY_CONDITIONED_LATENT roots; analysis spec v3 reports the classes descriptively. Search invariance: the clean-state simulation's
results digest is unchanged (`0b0bb1fd84c224bb…`). Engineering observation (simulation, not evidence): all
6 latent witnesses were continuation-triggered.

## Amendment v1.3 — analysis interpretation (found before any data)
- **Endpoint:** suffix-free arms (the no-suffix ablation and all five search baselines) cannot emit a latent witness by construction. Their latent fields are now `N/A`, never zero. The inferential no-suffix family and the no-suffix latent survival curve are removed (`science/ANALYSIS_SPEC_v4.md`).
- **RQ2:** now rests on adjudicated root-cause overlap, suffix-specific roots, the full arm's latent witnesses and descriptive timing, and attribution.
- **Producer classes:** the registry validator enforces that the root-cause ledger is post-run manual only.
- **QA evidence:** regenerated from one tree (`qa/QA_PROVENANCE.json`): 240 tests, 0 failed, 0 skipped.

## Amendment v1.4 — matched random-suffix isolation (pre-execution scientific amendment)
- **Change:** one full-campaign arm, `ablate_random_suffix`: 90 units, matched seeds, same key and length, never calls the synthesizer.
- **Analysis:** RQ2a (descriptive attribution and overlap) and RQ2b (inferential family on latent-only time, Holm over three targets), per ANALYSIS_SPEC_v5.
- **Adjudication:** protocol v3, with two adjudicators and agreement/kappa.
- **Baselines:** BASELINE_FIDELITY_REPORT.md.
- **Matrix:** 873 units, 3,840 slot-hours, 40.0 days at 4 measured slots; 3 slots block.
- **Verification:** 255 tests, 0 failed. Search semantics hold on paired simulation units.

## Amendment v1.5 — RQ2b matched-pair inference (analysis only)
- **Inference:** an exact two-sided sign test on per-target matched win/loss, with a Clopper–Pearson 95% interval and Holm over the valid target-level tests (reduced family size reported). KM curves are descriptive only. RQ2b has no Mann–Whitney, A12 or log-rank output.
- **Pair integrity:** exactly one pair per target × workload × repetition, with identical seed, budget, applicability, workload, target and repetition. Otherwise `RQ2B_ANALYSIS_BLOCKED`, with no unpaired fallback.
- **Unchanged:** matrix (873 / 270 / 90 / 3,840 slot-hours). Unit results and witnesses are byte-identical to v1.4 in simulation.
- **Tests:** 263 passed, 0 failed.
