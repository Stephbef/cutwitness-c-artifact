# CutWitness-C — Pre-Execution Attribution Amendment v1.2

Status: issued before any real-target execution. Classification: **pre-execution evidence-classification amendment**; no change to
treatment, search, scheduling, seeds, budgets, triage, pilot criteria, targets, workloads, baselines or statistical families.

## Problem
latent(h) := FC(h) and not CC(h). A failure of FC(h.c) does not by itself show that h left corrupted state: the continuation c may
trigger a defect even from a correct state at src(h). Patch-2 records no replay that separates the two.

## Change
At S8, after witness closure, for every reproducible latent witness (status NEW, latent):
- E1: execute h, verify FC(h), execute the characterization continuation c, record the result;
- E2: fresh target instance; load exactly src(h) as one transaction (no history replay, no lifecycle events); verify the final cut;
  execute the same c; record the result.
Each path is replayed `nondet_reruns` (10) times; replays must be identical.
Classes: E1 fails and E2 passes -> HISTORY_CONDITIONED_LATENT; both fail -> CONTINUATION_TRIGGERED; non-identical replays, errors,
E1 not latent on replay, or E2 failing at the cut -> UNRESOLVED_ATTRIBUTION.
Output: `attribution/<witness>.json` (resumable per witness) and `analysis/.../latent_attribution.csv`
(witness_id, target, workload, final_cut_digest, continuation_digest, history_path_result, fresh_cut_result, attribution_class, reason, replays_per_path).

## Coupled documents
ROOT_CAUSE_ADJUDICATION_PROTOCOL_v2.md (Section J), science/ANALYSIS_SPEC_v3.md, MANUSCRIPT_EVIDENCE_REGISTRY.csv rows for attribution.
