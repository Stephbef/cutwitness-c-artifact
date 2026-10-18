# Search-semantics comparison: CutWitness-C vs matched random suffix

Source: clean-state engineering simulation (ENGINEERING VALIDATION ONLY — NOT SCIENTIFIC RESULTS), logical budgets, paired units sharing the same matrix cell and trial seed.

Paired cells: 9. Identical executed candidate histories, history lengths and requested suffix lengths in every pair: **True**.

| Cell | Search executions | Identical (history, length, suffix length) | Suffixes present | Suffix content differs | CW latent candidate | Random latent candidate |
|---|---:|---|---:|---:|---|---|
| `full|feldera|W1|·|0` | 3 | True | 0 | 0 | False | False |
| `full|feldera|W2|·|0` | 3 | True | 0 | 0 | False | False |
| `full|feldera|W3|·|0` | 2 | True | 1 | 1 | True | True |
| `full|pg_ivm|W1|·|0` | 3 | True | 0 | 0 | False | False |
| `full|pg_ivm|W2|·|0` | 3 | True | 1 | 1 | True | False |
| `full|pg_ivm|W3|·|0` | 2 | True | 2 | 2 | True | True |
| `full|risingwave|W1|·|0` | 3 | True | 0 | 0 | False | False |
| `full|risingwave|W2|·|0` | 3 | True | 0 | 0 | False | False |
| `full|risingwave|W3|·|0` | 3 | True | 3 | 3 | False | False |

The arms differ only where the suffix-construction rule acts (suffix content). Every other executed quantity is identical, which is the matching contract's mechanical guarantee. Latent-candidate columns are engineering observations of the toy engines, not evidence about the real targets.
