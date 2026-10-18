# One-Shot Execution Amendment (pre-registered before any result exists)

1. The science of CutWitness-C is unchanged (scientific freeze: science/SCIENTIFIC_FREEZE_CUTWITNESS_C.md).
2. The optional post-pilot redesign permitted by the freeze is **waived**.
3. The pilot is an automatic gate inside the same sealed RUN_ID.
4. If the pilot passes (any frozen signal A–D), the same run proceeds automatically to the full campaign.
5. If no pilot signal appears, the campaign stops with final status `COMPLETE_PILOT_NO_GO`.
6. No redesign is performed using pilot outcomes. No TEST parameter may change.
7. Operational preflight failures occurring before any scientific unit is created are labeled `NOT_STARTED_OPERATIONAL`.
8. A crash after scientific units begin may only be resumed from the same journal, same run_id, same hashes and same schedule; committed units are never rerun; seeds are never substituted.
9. This is a conservative pre-registered change, not outcome tuning. Its SHA-256 is recorded in campaign/FROZEN_CAMPAIGN.yaml.
