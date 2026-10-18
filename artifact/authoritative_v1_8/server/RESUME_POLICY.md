# Resume Policy

- A run is identified by an immutable `run_id` sealed in `run_meta.json` with the frozen-config digest; any config or code change makes the controller refuse to continue.
- The journal (`journal.jsonl`) is append-only and hash-chained. A torn final line from a crash is moved to `journal.jsonl.torn` and recorded (`TORN_TAIL_RECOVERED`); any interior corruption stops the run (`INCOMPLETE_NONRESUMABLE_CORRUPTION`).
- Unit states: PLANNED, RUNNING, COMMITTED, FAILED_OPERATIONAL, INVALID_SCIENTIFIC, UNRESOLVED, NOT_APPLICABLE. COMMITTED and NOT_APPLICABLE units are never rerun.
- A unit found RUNNING after a crash is recorded as an interrupted attempt and retried with the same seed (at most 2 operational retries per invocation).
- Image digests and dataset digests journaled before the first scientific unit must be identical on resume.
- One controller at a time (exclusive lock). Resume command: `./run_one_shot.sh runs/cutwitness_c` (same run directory).
- Verified by the nine-point crash matrix (`qa/CRASH_MATRIX.json`): every resumed run reproduces the uninterrupted FINAL_RESULTS_DIGEST.
