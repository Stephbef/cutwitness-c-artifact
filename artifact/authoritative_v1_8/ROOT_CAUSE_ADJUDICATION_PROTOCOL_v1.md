# Root-Cause Adjudication Protocol v1 (pre-registered before any real execution)

Status: frozen with Patch-2; SHA-256 recorded in `campaign/FROZEN_CAMPAIGN.yaml` (`evidence.adjudication_protocol`).
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
methods_detecting, confidence_status (ADJUDICATED | UNRESOLVED_KEPT_SEPARATE)`.
Validated by `python3 -m cutwitness.adjudication validate <ledger.csv> <witnesses_dir> [external_report_ledger.csv]`.

## H. External reports
Developer issue status lives only in `external_report_ledger.csv`
(`report_id, root_cause_ids, target, tracker_reference, status, status_date, note`). Reports reference existing root causes and can
never create, merge or remove a scientific root cause; status changes do not alter scientific counts.

## I. Who and when
Adjudication starts after S12 of the frozen campaign. Two adjudicators work independently on the blind worksheet; disagreements
are resolved by keeping the witnesses separate (rule F). The ledger is hashed and archived with the run before any manuscript number
is replaced.
