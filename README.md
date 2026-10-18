# Anonymous artifact: Beyond the Current Cut: Testing Hidden State in Incremental View Maintenance

**Public-release status:** anonymous V1.8 implementation, frozen scientific design, protocols, analysis code, tests, and reproducibility machinery.

## Important evidence boundary

This public repository contains **no predictive, best-case, or synthetic scientific result tables from manuscript planning**. Those planning-result artifacts and the pre-server manuscript have been removed from this release.

Engineering simulations remain under clearly named QA/configuration paths and are used only to test the software pipeline; they are not scientific evidence.

No observed campaign result bundle is fabricated here. If a sealed observed-results bundle is available, place it under `results/` exactly as required by the documented pipeline.

## Reviewer quick start

1. `cd artifact/authoritative_v1_8`
2. `python3 tools/verify_package.py`
3. `sha256sum -c SHA256SUMS`
4. `python3 -m pytest -q` for engineering QA.
5. Optional toy-engine QA: `python3 -m cutwitness.one_shot --config campaign/ENGINEERING_SIMULATION.yaml --run-dir /tmp/sim`
6. At repository root, `python3 scripts/submission_readiness.py` checks package integrity, anonymity, and whether a sealed observed-results bundle is present.

## Layout

| Path | Contents |
|---|---|
| `artifact/authoritative_v1_8/` | V1.8 code, frozen campaign design, protocols, analysis specification, tests, and QA evidence |
| `results/` | Reserved for a sealed observed-results bundle; no planning-result substitute is included |
| `PUBLIC_RELEASE_CLEANING_REPORT.md` | Exact record of planning-result material removed for this public release |

## Key documents

- `artifact/authoritative_v1_8/PREEXECUTION_AMENDMENT_V1_8_DELETION_MATCHED_CONTROL.md`
- `artifact/authoritative_v1_8/science/ANALYSIS_SPEC_v7.md`
- `artifact/authoritative_v1_8/SERVER_HANDOFF.md`
- `artifact/authoritative_v1_8/ROOT_CAUSE_ADJUDICATION_PROTOCOL_v4.md`
- `ANONYMITY.md`
- `REPRODUCIBILITY.md`
