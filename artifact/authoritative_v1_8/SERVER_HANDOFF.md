# SERVER HANDOFF — operator procedure

> **V1.8 pre-execution amendment** (`PREEXECUTION_AMENDMENT_V1_8_DELETION_MATCHED_CONTROL.md`). It adds the deletion-matched control: RQ2c, a new arm of 90 units.
> The campaign becomes 963 units and 4,200 slot-hours (43.75 days at 4 slots), with analysis spec v7 and 318 tests passing.
> Figures below that say 873 units, 3,840 slot-hours, 40 days or 307 tests refer to V1.7.2 and are superseded.


Allowed actions: provide the token, extract, verify, run the single command, monitor, resume the same run after an operational interruption.
Forbidden: editing any file, changing versions, seeds, budgets, adapters, SQL, oracle rules or pilot criteria.
`run_one_shot.sh` executes the steps below in this order and stops at the first failure; no command or flag bypasses a gate.

| # | Step | How it happens | Stop condition |
|---|---|---|---|
| 1 | Verify package hashes | `python3 tools/verify_package.py` (also `sha256sum -c SHA256SUMS`) | any mismatch or unlisted file → `NOT_STARTED_OPERATIONAL` |
| 2 | Inspect server resources | controller S1 fingerprint + S2 measured CPU/RAM/disk/ports | — (recorded) |
| 3 | Resolve/verify image digests | S2 pulls `risingwavelabs/risingwave:v3.1.0`, `ghcr.io/feldera/pipeline-manager:0.366.0`; journals digests; resume requires identical digests | digest change → `INCOMPLETE_NONRESUMABLE_CORRUPTION` |
| 4 | Build pg_ivm image | S2 `docker build server/targets/pgivm` (PostgreSQL 17.10, pg_ivm @ 22b4b452…); image ID journaled | build failure → stop |
| 5 | Real-target conformance: pg_ivm, Feldera, RisingWave | S4 launches per-slot containers (cpuset, 32 GiB, loopback ports), checks readiness and exact versions, runs live conformance | |
| 6 | Stop immediately if any target fails | S4 | `CONFORMANCE_BLOCKED` / `CAPABILITY_BLOCKED`; no pilot unit is created |
| 7 | Token only via environment | `export CUTWITNESS_W1_TOKEN=...` before step 1 | missing → `NOT_STARTED_OPERATIONAL` |
| 8 | Materialize W1 data | S3 (frozen selection rule, VALIDATION/TEST firewall, licence classes); W2/W3 deterministic | non-reproducible materialization on resume → corruption verdict |
| 9 | Measured-resource / duration preflight | S2 `CAMPAIGN_PREFLIGHT_REPORT.txt` written to `runs/.../preseal/` | |
| 10 | Require ≤ 45 days | S2 | `CAMPAIGN_DURATION_PREFLIGHT=BLOCKED` → `NOT_STARTED_OPERATIONAL` |
| 11 | Execute pilot | S6 (48 units, 12 h each) | |
| 12 | Apply frozen A–D decision | S6, automatic | no signal → `COMPLETE_PILOT_NO_GO` |
| 13 | Only if GO, continue full campaign | S7 (+ S5 tester conformance before S6) | incomplete units → `INCOMPLETE_OPERATIONAL_RESUMABLE` |
| 14 | Archive journal/results | S8 witnesses, S9–S10 analysis, S11 `SHA256SUMS` + `final_manifest.json`, S12 `FINAL_VERDICT.json` | archive the whole run directory |

Note on ordering: the controller performs the duration preflight (steps 9–10) before deployment so that an infeasible host never starts
containers; real-target conformance (steps 5–6) still precedes every scientific unit.

## Commands
```
export CUTWITNESS_W1_TOKEN=...            # never written to disk
./run_one_shot.sh runs/cutwitness_c        # start; the same command resumes
cat runs/cutwitness_c/FINAL_VERDICT.json   # terminal verdict
tail -f runs/cutwitness_c/journal.jsonl    # monitor without modifying anything
```
Verdicts: `COMPLETE_PILOT_NO_GO`, `COMPLETE_FULL_CAMPAIGN`, `NOT_STARTED_OPERATIONAL`, `CAPABILITY_BLOCKED`, `CONFORMANCE_BLOCKED`,
`INCOMPLETE_OPERATIONAL_RESUMABLE` (re-run the same command), `INCOMPLETE_NONRESUMABLE_CORRUPTION`. Resume rules: `server/RESUME_POLICY.md`.
