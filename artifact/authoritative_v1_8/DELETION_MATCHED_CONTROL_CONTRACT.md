# Deletion-matched continuation control: matching contract (V1.8)

**Matched to the directed continuation:**
- candidate history (shared search stream);
- target key;
- length;
- exact number of delete steps;
- guidance, reduction, lifecycle placement and O4 cadence;
- seed and budget.

**Randomized:**
- the positions of the delete steps;
- which same-key row each delete removes, with legal foreign-key cascades;
- insert contents, following the frozen random-insert rule.

**Legality.** Every prefix is legal. An infeasible order is resampled at most 16 times; if all fail, the opportunity has no continuation (fail closed).

**Stream.** `sha256("deletion-matched|seed|exec")`, independent of the search and random-suffix streams.

**Witness closure.** Units of this arm are processed after every V1.7.2 arm, so V1.7.2 witness content is unchanged.

The full rationale and accounting are in `PREEXECUTION_AMENDMENT_V1_8_DELETION_MATCHED_CONTROL.md`.
