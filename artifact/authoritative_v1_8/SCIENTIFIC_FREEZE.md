# Scientific Freeze — CutWitness-C (authoritative summary for this package)

> **V1.8 pre-execution amendment** (`PREEXECUTION_AMENDMENT_V1_8_DELETION_MATCHED_CONTROL.md`). It adds the deletion-matched control: RQ2c, a new arm of 90 units.
> The campaign becomes 963 units and 4,200 slot-hours (43.75 days at 4 slots), with analysis spec v7 and 318 tests passing.
> Figures below that say 873 units, 3,840 slot-hours, 40 days or 307 tests refer to V1.7.2 and are superseded.


Title (fixed): *Beyond the Current Cut: Testing Hidden State in Incremental View Maintenance*. This supersedes the working title recorded in sealed documents; see `TITLE_AND_PROTOCOL_NOTICE.md`.

- Properties: final-cut convergence FC(h): O(M_S(h)) = F(V, src(h)); path convergence PC; continuation closure CC(h): ∀ legal c, FC(h·c). Latent divergence: FC holds, CC fails.
- Histories: Z-set transactions + source-neutral lifecycle events {RESTART, KILL_RECOVER, CHECKPOINT, RESTORE_LATEST, RESCALE, UPGRADE, REPLACE_VIEW_IDENTICAL, COMPACT}; every prefix legal (multiplicities ≥ 0, PK, FK, NOT NULL).
- Supported subset: σ, π, inner/left-outer equi-join, GROUP BY (≥1 key) with COUNT/SUM/AVG/MIN/MAX, DISTINCT, per-partition top-k (deterministic tie-break on all columns). Exact types only (BIGINT, DECIMAL(18,4), ASCII VARCHAR). AVG canonicalized as exact SUM/COUNT quantized to 6 decimals (half-even).
- Independence: context-sensitive logical-key independence I_x; reduction relation ≡_K = identical lifecycle-annotated per-key input sequences (sound only for E_loc; ρ = 0.10 non-canonical sampling).
- Fault models: E_loc (per-(operator,key) machines, key-faithful, per-key recovery maps); E_k^D (k-window key-symmetric activation, state-corruption effect).
- Theorems: P2/P2′ (proved, standard trace argument, new mapping); P3 reformulated with Lemma D (characterization-suffix detection for exposed operators); no claims outside these classes.
- Semantic transition automata: frozen version sta/1 (see cutwitness/sta.py), k = 2 primary coverage.
- Oracles O1 clean rebuild, O2 path-vs-path, O3 independent reference (DuckDB), O4 per-step continuation.
- Ordered triage: infrastructure, unsupported, nondeterminism (10 re-executions, all identical required), canonicalization, reference bug, expected, lifecycle/recovery, maintenance. Only the last two can be candidate bugs, after ≥2 reproductions and reference/O3 agreement.
- Witnesses: slice-1-minimal (suffix, lifecycle, inverse pair, ddmin, single event/row fixpoint) with certificate.
- RQs, baselines, ablations, statistics and bug accounting as in the frozen co-design (unchanged).

## Execution protocol in force (Amendment v1.1, pre-execution)
- Full-campaign stochastic search trials: 10 repetitions × 4 h; pilot: 3 repetitions × 12 h, tools and A–D thresholds unchanged.
- Six execution-unit classes (SEARCH_TRIAL, DETERMINISTIC_SUITE, MINIMIZATION, SECONDARY_ORACLE, ABLATION, NOT_APPLICABLE); every baseline family retained.
- Targets: PostgreSQL 17.10 + pg_ivm 1.16, Feldera 0.366.0, RisingWave 3.1.0 — UPGRADE excluded on all three.
- Workloads: W1 (real GTFS histories; 20 routes sampled per feed; feeds need ≥ 12 datasets), W2 (TPC-H-shaped, not dbgen byte-identical; SUM(l_extendedprice)), W3 (generated).
- 45-day fail-closed duration gate on measured resources; no bypass.

The retired F1 reuse science (historical witness search, K-contracts, N0–N6, planning ledgers) is provenance only (`legacy/README.md`) and is
not part of this freeze.
