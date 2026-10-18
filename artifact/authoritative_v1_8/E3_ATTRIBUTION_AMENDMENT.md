# Pre-Execution Amendment v1.6 — E3 Canonical Incremental Replay (attribution only)

Status: issued before any real execution.
Base: server package V1.5.2 (`b09fadb3…`), commit `2a8180f`.

**Why.** The adversarial PC review (R4-W3) showed that the history-conditioned (HC) label rests on E1-fail / E2-pass. E2 loads src(h)
in one bulk transaction and may exercise an initialization path that differs from incremental maintenance.

**Change.**
- Add E3, the canonical incremental replay (E3_CANONICAL_REPLAY_CONTRACT.md).
- HC now requires E2 **and** E3 to pass; CT requires both to fail.
- E2/E3 disagreement is UNRESOLVED (PATH_CONSTRUCTION_SENSITIVE).
- Adjudication protocol v4 adds Section J′ (this rule) and Section M (witness-to-root merge decisions recorded separately from class labels).

**Unchanged.** Search, candidate generation, triage, all campaign units (873), the matrix, seeds, budgets, treatments, the pilot, every
analysis family and the RQ structure. Attribution remains descriptive (RQ2a); no inferential test uses it.

**Decision rule (unchanged in spirit).** The HC count is reported with both reconstructions shown. A root with any
PATH_CONSTRUCTION_SENSITIVE witness is not counted as HC.

**Not authorized here (recorded as an open item).** The frozen search does not tag ρ-sampled non-canonical members, nor compare them
with their class representative. The manuscript therefore reports no ρ-sampling falsification outcome, and the claim that an
intra-class divergence is "a witness of out-of-model behavior" is withdrawn. A behaviour-neutral instrumentation amendment would be
needed to report it.
