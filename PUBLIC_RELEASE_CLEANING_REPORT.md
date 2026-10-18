# Public release cleaning report

Purpose: remove manuscript-planning scientific result material from the anonymous public artifact without inventing observed outcomes.

Removed:
- the pre-server manuscript PDF and TeX under `manuscript/`;
- the top-level result-to-paper placeholder map;
- the historical implementation diff that embedded obsolete placeholder registry rows.

Sanitized:
- the evidence registry and its generator now use `OBSERVED_OUTPUT_REQUIRED` rather than a planning-result placeholder status;
- the V1.4 amendment record states that no forecast result values are included;
- top-level documentation no longer directs reviewers to planning-result values.

Preserved:
- V1.8 source code;
- frozen campaign design and amendments;
- analysis specifications;
- root-cause adjudication protocols;
- tests;
- engineering QA/simulation machinery, clearly separated from scientific evidence;
- anonymization and security checks.

No observed campaign result was generated, inferred, or substituted during this cleaning step.
