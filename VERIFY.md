# Package verification

From `artifact/authoritative_v1_8/`:

1. Run `python3 tools/verify_package.py`; it must print `PACKAGE_VERIFY PASS`.
2. Run `sha256sum -c SHA256SUMS`; every listed file must verify.
3. `manifests/PREEXECUTION_MANIFEST.json` records the exact public-release file inventory and scientific/operational digests.
4. Rerunning `python3 tools/make_manifest.py` on a clean copy should reproduce the manifest for the same tree.

At repository root, verify `REPOSITORY_SHA256SUMS` against the complete public-release tree.
