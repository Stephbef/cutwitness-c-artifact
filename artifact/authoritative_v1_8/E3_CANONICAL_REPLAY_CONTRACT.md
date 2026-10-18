# E3 Canonical Incremental Replay — Contract (Amendment v1.6)

**Purpose.** Separate "the original incremental path matters" from "the bulk-load/initialization path differs from the incremental path".
E2 alone cannot do this, because loading src(h) in one transaction can exercise a different engine path.

**Definition.** E3 = a fresh instance; apply `canonical_history(schema, h)`; check the final cut (O1); apply the same continuation c,
checking every step (O4); repeat `nondet_reruns` times; replays must be identical.

**Canonical history** (`cutwitness/attribution.py: canonical_history`):
- reaches exactly src(h) (checked);
- inserts only, one row per transaction, ordinary incremental transactions;
- tables in schema order (parents before children), rows in canonical sorted order, so every prefix satisfies keys and foreign keys (checked);
- no lifecycle actions;
- deterministic: a pure function of src(h), independent of the target's hidden state;
- does not reproduce h: if the canonical sequence equals h's transaction sequence, rows are emitted in reverse order within each table;
  if it still coincides, attribution is UNRESOLVED ("canonical reconstruction coincides with the original history").

**Scope.** Post-witness replay at S8 only, on reproducible continuation-latent witnesses.
- No campaign unit is added, and search, candidate discovery, triage, seeds, budgets, treatment and the pilot are untouched.
- `tests/test_e3_attribution.py::test_e3_does_not_touch_search` checks this structurally; the simulation proves it byte-for-byte (results and witnesses identical to v1.5.2).

**Outputs.**
- `attribution/<witness>.json` (resumable per witness) gains `canonical_path_result`, `canonical_transactions`, `canonical_independent_of_history` and `attribution_detail`.
- `latent_attribution.csv` carries the same columns.
