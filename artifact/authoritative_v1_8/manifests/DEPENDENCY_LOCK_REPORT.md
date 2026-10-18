# Dependency lock report (generated)

## Third-party imports in active source

- `duckdb` — used by cutwitness/adapters/mocks.py, cutwitness/oracles.py, cutwitness/toyengine.py
- `psycopg` — used by cutwitness/adapters/transport.py

No other third-party module is imported by `cutwitness/` (numpy and scipy are not dependencies; statistics are stdlib-only and verified against a frozen scipy reference fixture).

## Runtime lock (`vendor/requirements.lock`, installed offline with `--no-index --require-hashes`)

- `duckdb==1.1.3 --hash=sha256:4ebf5f60ddbd65c13e77cddb85fe4af671d31b851f125a4d002a313696af43f1`
- `psycopg==3.2.10 --hash=sha256:ab5caf09a9ec42e314a21f5216dbcceac528e0e05142e42eea83a3b28b320ac3`
- `psycopg-binary==3.2.10 --hash=sha256:14bcbcac0cab465d88b2581e43ec01af4b01c9833e663f1352e05cb41be19e44`
- `typing-extensions==4.12.2 --hash=sha256:04e5ca0351e0f3f85c6853954072df659d0d13fac324d0072316b67d7794700d`

## QA lock (`vendor/requirements-qa.lock`, tests only)

- `pytest==8.3.5 --hash=sha256:c69214aa47deac29fad6c2a4f590b9c4a9fdb16a403176fe154b79c0b4d4d820`
- `iniconfig==2.0.0 --hash=sha256:b6a85871a79d2e3b22d2d1b94ac2824226a63c6b741c88f7ae975f18b6778374`
- `packaging==24.2 --hash=sha256:09abb1bccd265c01f4a3aa3f7a7db064b36514d2cba19a2f694fe6150451a759`
- `pluggy==1.5.0 --hash=sha256:44e1ad92c8ca002de6377e165f3e0f1be63266ab4d554740532335b9d75ea669`

## Bootstrap

- `pip-24.2-py3-none-any.whl` (vendored; executed directly from the wheel inside a `--without-pip` venv)

Clean offline installation into a fresh venv from the wheelhouse is exercised by `tests/test_packaging.py` (wrapper) and by the fresh-extraction verification.
