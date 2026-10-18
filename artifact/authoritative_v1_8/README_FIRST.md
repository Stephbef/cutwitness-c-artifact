# README FIRST — CutWitness-C pre-execution server handoff

> **V1.8 pre-execution amendment** (`PREEXECUTION_AMENDMENT_V1_8_DELETION_MATCHED_CONTROL.md`). It adds the deletion-matched control: RQ2c, a new arm of 90 units.
> The campaign becomes 963 units and 4,200 slot-hours (43.75 days at 4 slots), with analysis spec v7 and 318 tests passing.
> Figures below that say 873 units, 3,840 slot-hours, 40 days or 307 tests refer to V1.7.2 and are superseded.


> **V1.7.2:** ρ bookkeeping keyed by history digest (evidence-producer fix; zero search change); see `V1_7_2_RHO_BOOKKEEPING_FIX_RECORD.json`.
>
> **V1.7.1 (documentation only):** title and post-run protocol references updated; see `TITLE_AND_PROTOCOL_NOTICE.md`. Code, configs, campaign matrix and tests were byte-identical to V1.7 in V1.7.1.

**Local closure verdict: `BLOCKED — real-target conformance not yet executed`.**

## What this package is
The complete, frozen implementation of CutWitness-C (*Beyond the Current Cut: Testing Hidden State in Incremental View Maintenance*): source, tests,
frozen campaign configuration, Amendment v1.1, real-target deployment definitions, an offline hash-locked Python wheelhouse, and one
fail-closed entry point (`run_one_shot.sh`). No real scientific campaign has been run and no scientific result exists.

## Simulated versus real
- **Real targets** (PostgreSQL 17.10 + pg_ivm 1.16, Feldera 0.366.0, RisingWave 3.1.0) have **not** been executed: the build environment had no
  container runtime (1 vCPU, 3 GiB). Their adapters are verified only against protocol mocks (`qa/MOCK_CONFORMANCE.json`), which can never satisfy
  the real-target gate.
- Everything under `qa/` and any run of `campaign/ENGINEERING_SIMULATION.yaml` or `campaign/CRASHTEST_SIMULATION.yaml` is
  **ENGINEERING VALIDATION ONLY — NOT SCIENTIFIC RESULTS**.

## Why the status is BLOCKED locally
READY requires live conformance of all three pinned real targets. That gate (S4) runs on the server, inside the campaign controller, before any
pilot unit. If any target fails, the campaign stops with `CONFORMANCE_BLOCKED` or `CAPABILITY_BLOCKED`.

## First server command
```
export CUTWITNESS_W1_TOKEN=<Mobility Database refresh token>    # environment only; never in files
./run_one_shot.sh runs/cutwitness_c
```
Re-running the same command with the same run directory resumes the same sealed run.

## Required environment
- Linux x86_64, Python 3.12 (system interpreter only for bootstrap; dependencies come from `vendor/wheels`), Docker CLI and daemon, network
  access to pull the pinned images and to reach the Mobility Database API.
- Hardware: the campaign needs `TOTAL_SLOT_HOURS = 3840` (v1.4/v1.5 matrix: 873 units, 270 ablations, 90 matched random-suffix units).
  With **4 measured effective slots** that is 960 h, i.e. 40.0 days, which passes the ≤ 45-day gate. With 3 measured effective slots it is
  1,280 h, i.e. 53.33 days, and the gate blocks. Four slots is planning arithmetic, not an observed server fact: S2 must *measure* the
  effective slots on the host (each slot is 8 vCPU / 32 GiB, with 2 vCPU / 8 GiB host reserve and 100 GiB disk per slot).
- Minimum server: four effective slots require at least 34 available vCPUs, 136 GiB RAM and 500 GiB free disk under the frozen
  `server_requirements` (campaign/FROZEN_CAMPAIGN.yaml). 500 GiB is the actual minimum accepted by the frozen S2 server preflight. Of it,
  400 GiB corresponds to the four 100-GiB execution-slot allowances; the remaining 100 GiB is non-slot/host headroom.

## Expected first gates
1. package integrity (SHA-256 manifest); 2. offline hash-checked install; 3. security scan; 4. token and Docker presence;
5. S2 measured-resource / 45-day duration preflight and image-digest resolution; 6. S3 W1/W2/W3 materialization;
7. **S4 real-target deployment, readiness, exact versions and live conformance (pg_ivm, Feldera, RisingWave)**; 8. S5 tester conformance;
9. S6 pilot with the frozen A–D decision.

## Reports
`SERVER_HANDOFF.md` (operator procedure) · `SCIENTIFIC_FREEZE.md` · `CUTWITNESS_C_PREEXECUTION_FEASIBILITY_AMENDMENT_v1_1.md` ·
`AMENDMENT_v1_1_RECORD.json` · `CAMPAIGN_MATRIX.csv` · `CAMPAIGN_PREFLIGHT_REPORT.txt` · `IMPLEMENTATION_CLOSURE_REPORT.md` ·
`TEST_REPORT.md` · `SECURITY_SCAN_REPORT.md` · `MANUSCRIPT_EVIDENCE_REGISTRY.csv` · `ROOT_CAUSE_ADJUDICATION_PROTOCOL_v4.md` (post-run; v3 superseded, before any manuscript number is replaced; v1 kept for provenance) · `science/ANALYSIS_SPEC_v6.md` (earlier versions kept for provenance) · `PATCH2_RECORD.json` · `CUTWITNESS_C_PREEXECUTION_ATTRIBUTION_AMENDMENT_v1_2.md` · `AMENDMENT_v1_2_RECORD.json` · `AMENDMENT_v1_3_RECORD.json` · `SCIENTIFIC_AMENDMENT_v1_4.md` · `AMENDMENT_v1_4_RECORD.json` · `AMENDMENT_v1_5_RECORD.json` · `RELEASE_HYGIENE_v1_5_1_AUDIT.md` · `RELEASE_HYGIENE_v1_5_1_RECORD.json` · `RELEASE_HYGIENE_v1_5_2_RECORD.json` · `E3_ATTRIBUTION_AMENDMENT.md` · `E3_CANONICAL_REPLAY_CONTRACT.md` · `ROOT_CAUSE_ADJUDICATION_PROTOCOL_v4.md` · `AMENDMENT_v1_6_E3_RECORD.json` · `EQUIVALENCE_SAMPLING_INSTRUMENTATION_AMENDMENT_v1.md` · `AMENDMENT_RHO_INSTRUMENTATION_v1_RECORD.json` · `RANDOM_SUFFIX_MATCHING_CONTRACT.md` · `BASELINE_FIDELITY_REPORT.md` · `SEARCH_SEMANTICS_COMPARISON.md` · `qa/QA_PROVENANCE.json` · `VERSION_PINS.md` · `SHA256SUMS` · `manifests/` · `qa/`.
