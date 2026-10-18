# Gate 0 — Final Novelty Memo (CutWitness-C)

**Verdict: PASS** (with residual risks listed below). Written before any implementation in this package.

## Obligation 1 — Enzyme (Databricks, SIGMOD Companion 2026; arXiv 2603.27775v2), read in full
- Section 5 "Ensuring Correctness": a Random Query Generator creates random schemas, data and SQL; for each query an MV is created, randomized source changes are applied, and the incremental refresh is compared with complete recomputation. A production A/B system compares MV contents with the defining query.
- Section 6 (experimental study) is performance-only (TPC-DI, comparison with a commercial IVM system).
- **Overlap:** randomized changes + incremental-vs-full-recompute oracle (= CutWitness-C baseline 1 and oracle O1).
- **Residual delta:** no source-equivalent histories, no lifecycle events, no continuation synthesis, no semantic transition words, no witness minimization.

## Obligation 2 — Materialize Zippy and platform-checks (source inspected: misc/python/materialize/zippy/{framework,scenarios,table_actions,view_actions,mz_actions}.py; misc/python/materialize/checks/{checks,scenarios,actions,mzcompose_actions}.py; test/zippy, test/platform-checks)
- Zippy: pseudo-random sequences of DDL/DML/failure actions; correctness validated against *watermarks* (tracked min/max of inserted integer ranges) through COUNT/COUNT DISTINCT/MIN/MAX views.
- Platform checks: hand-written `initialize → manipulate → validate` fragments executed under scenarios (no restart, restart, kill, upgrade, 0dt-upgrade, recovery).
- Keyword scan (equivalen*, permut*, reorder, shuffle, continuation, suffix, drain, probe, latent, characteriz*, transition, witness, minimi*, shrink): **no hits**.
- **Overlap:** randomized lifecycle-interleaved histories; validation after lifecycle events; hand-written manipulation after restart (a manual continuation).
- **Residual delta:** no comparison of source-equivalent histories; no synthesis of distinguishing continuations from reference state; no semantic transition words realized from a reference plan; no witness minimization.

## Targeted 2024–2026 check
Searched SIGMOD/PACMMOD/PVLDB, OSDI/SOSP/NSDI/EuroSys, PLDI/OOPSLA, ICSE/FSE/ISSTA/ASE (arXiv supplementary) for IVM testing, stream-processing correctness testing, stateful DBMS fuzzing, lifecycle/recovery testing, conformance testing of incremental state, source-equivalent history testing, continuation synthesis, latent-state corruption detection. Found: DiscPBT (2026, Spark batch meta-properties), Achilles (BTW 2025, query partitioning for stream engines), DiffStream (OOPSLA 2020), UpFuzz (NSDI 2026), DUPTester (SOSP 2021), recent SQLancer-family work (CODDTest PACMMOD 2025; SRS and "Equivalent Data Construction" SIGMOD 2026, title-level only). None tests IVM/streaming engines over source-equivalent update histories or synthesizes characterization suffixes.

## Conclusion
CutWitness-C survives. Exact residual delta: (1) continuation-closed latent-divergence witnesses with characterization suffixes synthesized from reference per-key state (Lemma D); (2) semantic transition automata whose k-words are realized by plan inversion; (3) per-key projection equivalence ≡_K as a stated-fault-model reduction; (4) lifecycle events as source-neutral history events in the same oracle.

## Unresolved risks
- R1: "Detecting Logic Bugs in DBMSs via Equivalent Data Construction" (SIGMOD 2026) read at title level only — must be read before submission.
- R2: Reviewers may frame the contribution as FSM conformance testing applied to IVM.
- R3: Vendor-internal tests may contain unpublished continuation checks (platform-checks manipulations are hand-written continuations).
