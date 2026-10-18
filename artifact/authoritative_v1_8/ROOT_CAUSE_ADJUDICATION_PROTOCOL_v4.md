# Root-Cause Adjudication Protocol v4 (pre-registered before any real execution; v3 plus Sections J′ and M)

Status: frozen with Amendment v1.2 (v1 frozen with Patch-2 is kept for provenance); SHA-256 recorded in `campaign/FROZEN_CAMPAIGN.yaml` (`evidence.adjudication_protocol`).
Root causes are a post-run adjudication layer above witness closure; they are never computed automatically.

## A. Input
Only **reproduced witnesses** (witness status `NEW` after S8: ten identical re-executions plus closure replay). For each:
target, workload, operators of the views, triage class, minimized witness (history and suffix), terminal digest, and the raw
engine and reference observations obtained by replaying the witness (`python3 -m cutwitness.replay`).
Demoted witnesses (`DEMOTED_NONDETERMINISM`) and non-candidate divergences are excluded.

## B. Unit
A root cause is one underlying target behaviour. One root cause may map to several witnesses; every witness maps to exactly one
root cause. A root cause never spans targets.

## C. Grouping rules
Two witnesses are merged only when evidence supports the **same underlying target behaviour**, e.g. the same per-key operator
state transition producing the same wrong state, demonstrated by minimized histories that reduce to the same semantic failure.
A merge is **never** justified solely by: matching operator family; matching error text; matching lifecycle event; similar-looking
output differences.

## D. Required evidence per decision
For every merge or split record: witness IDs; the semantic failure (expected vs observed state or output); the minimal histories;
operator and key evidence (which operator, which key, which transition); relation to lifecycle events (none / required / incidental);
reproduction evidence (replay result); written rationale. Merges additionally fill `merge_evidence`.

## E. Blindness
Adjudicate from `analysis/.../adjudication_worksheet.csv`, which carries no method identity. Open `witness_method_map.csv` only after
every root cause is fixed, and use it only to compute detection overlap (methods_detecting).

## F. Tie-breaking
If uncertain: **keep separate and mark `UNRESOLVED_KEPT_SEPARATE`**. Never force a merge. Unresolved rows are reported as such.

## G. Output
`root_cause_adjudication_ledger.csv` with columns
`root_cause_id, witness_ids (;-separated), target, workload, operator, primary_class (final-cut | path-convergence |
latent-continuation | lifecycle-sensitive), latent (true/false), lifecycle_annotation, adjudication_basis, merge_evidence,
methods_detecting, confidence_status (ADJUDICATED | UNRESOLVED_KEPT_SEPARATE), latent_attribution (HISTORY_CONDITIONED_LATENT | CONTINUATION_TRIGGERED | UNRESOLVED_ATTRIBUTION | NOT_LATENT), adjudicator_A_class, adjudicator_B_class, agreement (AGREE | DISAGREE), resolution, adjudicator_independence (AUTHORS_ONLY | INCLUDES_EXTERNAL)`.
Validated by `python3 -m cutwitness.adjudication validate <ledger.csv> <witnesses_dir> [external_report_ledger.csv]`.

## H. External reports
Developer issue status lives only in `external_report_ledger.csv`
(`report_id, root_cause_ids, target, tracker_reference, status, status_date, note`). Reports reference existing root causes and can
never create, merge or remove a scientific root cause; status changes do not alter scientific counts.

## I. Who and when
Adjudication starts after S12 of the frozen campaign. Two adjudicators work independently on the blind worksheet; disagreements
are resolved by keeping the witnesses separate (rule F). The ledger is hashed and archived with the run before any manuscript number
is replaced.

## J. Latent attribution (Amendment v1.2)
Every reproducible latent witness carries the S8 attribution record (`attribution/<witness>.json`, `latent_attribution.csv`):
E1 replays the history and its characterization continuation; E2 loads exactly src(h) into a fresh instance in one transaction and
applies the same continuation; each path is replayed `nondet_reruns` times and must be identical.
- A latent root cause is **history-conditioned** only if every witness assigned to it is HISTORY_CONDITIONED_LATENT.
- If any witness is CONTINUATION_TRIGGERED, the root cause is recorded as CONTINUATION_TRIGGERED: still a latent-continuation
  failure (the current-cut PASS did not certify the continuation), but no claim is made that the history corrupted state.
- UNRESOLVED_ATTRIBUTION witnesses make the root cause UNRESOLVED_ATTRIBUTION; they are never upgraded by argument.
- Claims of corrupted, path-dependent or history-left persistent state are made **only** for HISTORY_CONDITIONED_LATENT roots.
- Non-latent roots carry NOT_LATENT.

## K. Two adjudicators (Amendment v1.4)
- Two adjudicators classify every root independently from the blind worksheet: `adjudicator_A_class`, `adjudicator_B_class`.
- `agreement` is AGREE when both classes equal `primary_class`. Otherwise DISAGREE, and `resolution` records how it was resolved; by rule F, uncertain cases stay separate.
- Report raw agreement, and Cohen's kappa when at least two categories occur (`cutwitness.adjudication.agreement_stats`).
- `adjudicator_independence` states honestly whether only authors adjudicated. No external adjudicator is claimed unless one took part.
- Developer confirmation remains outside root-cause counting.

## L. Root-level comparison terms (RQ2a / RQ2b)
- **Suffix-stage-specific:** a continuation-latent root found by `cutwitness_c` but not by `ablate_no_suffix` at equal budget.
- **Characterization-specific:** a latent root found by `cutwitness_c` but not by `ablate_random_suffix` at equal budget.
- **CW-exclusive:** found by `cutwitness_c` but by none of the five stochastic search baselines.
- **Baseline-exclusive:** found only by search baselines.

These sets are reported separately and never merged.

## J′. Three-path attribution (Amendment v1.6, supersedes the attribution rule of Section J)
Every reproducible latent witness is replayed on three paths, each repeated `nondet_reruns` times and required to be identical:
E1 (original history then c), E2 (fresh instance, src(h) in one bulk transaction, then c), and E3 (fresh instance, src(h) reached by
the canonical incremental history of `cutwitness.attribution.canonical_history`, then c).
- **HISTORY_CONDITIONED_LATENT** (detail STRONG_HISTORY_CONDITIONED): E1 fails during c; E2 and E3 both pass c.
- **CONTINUATION_TRIGGERED**: E1 fails during c; E2 and E3 both fail c. No claim that h corrupted state.
- **UNRESOLVED_ATTRIBUTION**: E2 and E3 disagree (detail PATH_CONSTRUCTION_SENSITIVE), a reconstruction fails at the cut, the canonical
  history coincides with h, replays are non-identical, or an error occurs. Both reconstructions are always reported.
A root is history-conditioned only if all its latent witnesses classified HISTORY_CONDITIONED_LATENT under this rule.

## M. Witness-to-root merge decisions (recorded separately from class labels)
Before class labelling, each adjudicator records merge decisions for every candidate pair of witnesses on the same target and operator
family (`root_merge_decisions.csv`: pair_id, witness_a, witness_b, adjudicator_A_merge, adjudicator_B_merge, agreement, resolution).
Report the number of pair decisions, initial agreement, disagreements and their resolution. Cohen's kappa is reported only if both
decisions occur in sufficient number to be meaningful. Class-label agreement (Section K) is never presented as validation of merging.
Both adjudicators are authors unless stated otherwise; method-label blinding does not hide witness shape, and this is acknowledged.
