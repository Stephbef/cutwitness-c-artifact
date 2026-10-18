# CutWitness-C — Pre-Execution Scientific Amendment v1.4 (matched random-suffix isolation)

Status: issued before any real-target execution; no TEST observation exists.
Base: server package V1.3, commit `5280a02`, ANALYSIS_SPEC_v4, adjudication protocol v2.

## Why
The no-suffix ablation isolates *continuation stage present vs absent*. It does not isolate *reference-derived characterization suffix vs a matched arbitrary legal continuation on the same key*, which is the paper's distinctive mechanism claim.

## Change (exactly one added arm, full campaign only)
- **Arm:** `ablate_random_suffix`. Identical to `cutwitness_c` (guidance, reduction, semantic lifecycle placement, words, pairs, trial seed) except the suffix-construction rule.
- **Suffix rule:** a matched random legal continuation on the same exposed key with the same length |c_ref| (RANDOM_SUFFIX_MATCHING_CONTRACT.md). It never calls the characterization synthesizer.
- **Cells:** 3 targets × W1, W2, W3 × 10 repetitions × 4 h = 90 ABLATION units. Seeds reuse `cutwitness_c`'s trial seed for each cell and repetition (matched seed family); the suffix stream is derived separately.
- **Duration:** the matrix and 45-day preflight are regenerated from code (not hard-coded); see `CAMPAIGN_PREFLIGHT_REPORT.txt`.

## RQ2 structure (no new top-level RQ)
- **RQ2a — existence and attribution:** descriptive, co-primary root-level endpoints.
- **RQ2b — mechanism isolation:** inferential family `ablate_random_suffix` (ANALYSIS_SPEC_v5).

## Pre-registered decision rules (applied only after observed execution)
1. **Reference-suffix empirical claim survives** if full CutWitness-C shows a material advantage over the matched random suffix on at least one of: latent-only time to first divergence (RQ2b family), or characterization-specific adjudicated roots. Heterogeneity is reported exactly; universal dominance is not required.
2. **Random suffix matches full CutWitness-C everywhere:** remove the empirical claim. Retain only Lemma D as a scoped guarantee.
3. **Random suffix outperforms:** report it; no rhetorical rescue.
4. **History-conditioned latent roots** (protocol v3, Section J):
   - ≥ 3 across ≥ 2 engines: strong support for the historical-state framing;
   - 1–2: existence, not prevalence;
   - 0: re-examine "Historical Witnesses" in the title and framing before submission (no automatic rename).

## Unchanged
Title; FC, PC, CC; latent definition; E_loc; E_k^D; P2/P2′; Lemma D; P3; automata; plan inversion; CutWitness-C treatment; all existing baselines and ablations; targets; workloads; versions; SQL subset; 4 h budget; 10 repetitions; original seeds; TEST firewall; pilot criteria.

## Also frozen with v1.4 (process, no treatment change)
- Adjudication protocol v3: two adjudicators, agreement fields, raw agreement and Cohen's kappa.
- BASELINE_FIDELITY_REPORT.md.
