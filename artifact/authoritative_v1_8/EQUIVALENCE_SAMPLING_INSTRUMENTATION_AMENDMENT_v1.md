# Equivalence-Sampling Instrumentation Amendment v1 (pre-execution; observation only)

**Status.** Pre-execution. Base: server package V1.6 (`5343575e…`), commit `f13fb29`.

**Why.** The frozen search executes ρ = 0.1 of pruned ≡_K members as ordinary histories but neither tags them nor compares them with
their class representative. A falsification check of E_loc therefore had no evidence producer.

**What changes (logging only).** `run_trial` records, for CutWitness-C-type arms (`reduction is True`):
- **Per unit:** equivalence classes formed, members pruned, sampled members selected, and sampled members executed.
- **Per sampled member:**
  - `equivalence_class_id`, `representative_history_id`, `member_history_id`, `is_representative`, `selected_as_rho_sample`;
  - `rho_sampling_seed` (the unit seed) and the operator/key fingerprint;
  - `executed`, `representative_output_digest`, `sampled_member_output_digest` and `equal`;
  - `comparison_status`, one of MATCH, DIVERGENCE, REPRESENTATIVE_UNAVAILABLE, SAMPLE_ERROR, NONDETERMINISTIC or NOT_COMPARABLE.
  - Observation points are the final cut (O1) and every characterization-suffix step (O4).
  - Unavailable comparisons are never counted as matches.
- **Analysis:** `rho_sampling_observations.csv` and `rho_sampling_summary.csv` per target. Representative and member run in the same unit,
  so `representative_unit_id` equals the unit.

**What does not change.**
- History generation, class construction, the sampling probability, sampled-member selection (the random-number stream is consumed exactly
  as before), seeds, budgets, target calls, lifecycle placement, suffix generation, RQ2b and the 873-unit matrix are all untouched.
- `tests/test_rho_instrumentation.py::test_instrumentation_is_non_selection` runs the same trials with logging on and off and requires
  identical results apart from the new `rho_sampling` field.
- The simulation is compared with V1.6: identical execution logs, divergences, witnesses and matrix.

**Reporting rule.** Report only "among X sampled pruned members, Y intra-class disagreements were observed". Never write "E_loc held".

## V1.7.2 correction (bookkeeping key; still observation only)
- **Defect.** V1.7 tracked sampled members by Python `id()` of transient candidate tuples. Object ids are reused after objects are freed, so a sampled member whose history was regenerated and executed later was recorded only when its new tuple happened to receive the old address.
- **Effect.** Recorded ρ counts depended on memory layout. Local engineering validation reported 43 sampled, 6 executed and 4 comparable, versus the correct 43 sampled, 3 executed and 1 comparable.
- **Fix.** Bookkeeping is now keyed by history digest. Search, random-number consumption and selection are unchanged.
- **Regression tests.** Records are invariant to allocation perturbation, and every executed sample names an executed history.
