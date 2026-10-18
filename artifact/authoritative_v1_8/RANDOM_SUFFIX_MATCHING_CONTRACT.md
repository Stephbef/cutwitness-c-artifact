# Random-Suffix Matching Contract (Amendment v1.4)

The two arms differ **only** in the suffix-construction rule.

| Held fixed | How |
|---|---|
| target, workload, cell | same matrix cell (`CAMPAIGN_MATRIX.csv`) |
| trial seed family | `ablate_random_suffix` reuses `cutwitness_c`'s HMAC trial seed for the same cell and repetition (`matched_seed_of`) |
| search before the suffix stage | same tool configuration (guidance, reduction, semantic lifecycle, words, pairs) and same search RNG; the suffix uses a separate stream `sha256("random-suffix\|seed\|exec_index")`, so the search RNG is never consumed by the suffix |
| candidate history h, src(h), lifecycle prefix | consequence of the same seed and configuration; executions are verdict-independent (proven by `test_matched_arms_execute_identical_histories`) |
| exposed operator and key | same selection code: first exposed view of the candidate, first key in the reference order |
| opportunity | the same support conditions: `opportunity_length` raises exactly where `synthesize` does |
| suffix length | `opportunity_length` = \|c_ref\|, computed from the reference per-key state size only |
| legality, PK/FK/NOT NULL, domains | every step checked with `legal_state`; values from the schema's supported domains |
| O4 frequency | same judge: observation after every suffix step |
| budget | same 4 h per unit, same unit class (ABLATION) |

## Changed
`c = synthesize(...)` (reference-derived) becomes `c = random_suffix(...)` (matched random).

## Frozen sampling distribution (`cutwitness/suffix.py: RANDOM_SUFFIX_POLICY`)
- **Per step:** for joins, choose a side uniformly from {L, R}.
- **Insert vs delete:** if same-key row copies exist, insert with probability 0.5, else delete; with no copies, insert.
- **Delete:** a uniform row copy among those mapping to the key, with foreign-key cascade as in legal deletes.
- **Insert:** base row uniform over the source table's existing rows. Key columns are set to the key; PK is fresh; FK columns are kept; free columns are drawn uniformly from int {-1, 0, 1, 2, 3}, dec {-1, 0, 1, 2}, text {a, b, c}, with NULL at probability 0.1 for nullable columns.
- **Insert retries and fallback:** up to 8 attempts must map to the key; otherwise the same-key template.
- **Illegal insert:** replaced by a delete when possible; otherwise the opportunity is recorded as unsupported.
- **Excluded:** draining, extremum ordering, copy-by-copy removal, top-k boundary crossing, or two-sided join probing chosen *because* they distinguish states. Such sequences arise only by chance.

## Mechanical checks (`tests/test_random_suffix.py`)
- same key;
- same requested length as the characterization suffix;
- legality of every prefix;
- the random arm never calls `synthesize`;
- identical executed candidate histories in logical mode;
- latent endpoint applicable;
- disjoint inferential families;
- deterministic suffix RNG across re-execution;
- matrix arithmetic;
- the 45-day gate.
