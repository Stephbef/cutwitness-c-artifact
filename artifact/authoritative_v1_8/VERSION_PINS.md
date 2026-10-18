# VERSION_PINS

| Component | Version | Source identity (tag @ commit) | Image | Digest status |
|---|---|---|---|---|
| postgresql | 17.10 | REL_17_10 @ `25c49f3a4a742ba283f5cc43cc7f1d361552e917` | `postgres:17.10-bookworm` | SERVER_RESOLUTION_REQUIRED (journaled at S2) |
| pg_ivm | 1.16 | v1.16 @ `22b4b4520a3d2be896f07d3d55fb34772a5ecf8e` | `cutwitness/pg_ivm:frozen (built from server/targets/pgivm/Dockerfile)` | SERVER_RESOLUTION_REQUIRED (journaled at S2) |
| risingwave | 3.1.0 | v3.1.0 @ `45baf6460ea942e4ff57a5aa057d5b8db7f3b563` | `risingwavelabs/risingwave:v3.1.0` | SERVER_RESOLUTION_REQUIRED (journaled at S2) |
| feldera | 0.366.0 | v0.366.0 @ `4532aa1007e370ed4440527e39eebb76931896bc` | `ghcr.io/feldera/pipeline-manager:0.366.0` | SERVER_RESOLUTION_REQUIRED (journaled at S2) |
| DuckDB | 1.1.3 | PyPI wheel | — | wheel hash pinned |
| psycopg / psycopg-binary | 3.2.10 | PyPI wheels | — | wheel hashes pinned |

## Vendored wheels (SHA-256)

- `duckdb-1.1.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` `4ebf5f60ddbd65c13e77cddb85fe4af671d31b851f125a4d002a313696af43f1`
- `iniconfig-2.0.0-py3-none-any.whl` `b6a85871a79d2e3b22d2d1b94ac2824226a63c6b741c88f7ae975f18b6778374`
- `packaging-24.2-py3-none-any.whl` `09abb1bccd265c01f4a3aa3f7a7db064b36514d2cba19a2f694fe6150451a759`
- `pip-24.2-py3-none-any.whl` `2cd581cf58ab7fcfca4ce8efa6dcacd0de5bf8d0a3eb9ec927e07405f4d9e2a2`
- `pluggy-1.5.0-py3-none-any.whl` `44e1ad92c8ca002de6377e165f3e0f1be63266ab4d554740532335b9d75ea669`
- `psycopg-3.2.10-py3-none-any.whl` `ab5caf09a9ec42e314a21f5216dbcceac528e0e05142e42eea83a3b28b320ac3`
- `psycopg_binary-3.2.10-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` `14bcbcac0cab465d88b2581e43ec01af4b01c9833e663f1352e05cb41be19e44`
- `pytest-8.3.5-py3-none-any.whl` `c69214aa47deac29fad6c2a4f590b9c4a9fdb16a403176fe154b79c0b4d4d820`
- `typing_extensions-4.12.2-py3-none-any.whl` `04e5ca0351e0f3f85c6853954072df659d0d13fac324d0072316b67d7794700d`

UPGRADE is excluded on all targets. Python 3.12 on Linux x86_64 is required by the wheelhouse.
