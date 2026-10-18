# Scientific Freeze — CutWitness-C (authoritative summary for this package)

Title (fixed): *Beyond the Current Cut: Historical Witnesses for Durable Derived State*.

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
