# Reproducibility

- **Package:** every file is hash-pinned, and the 28 manifest identities are reproducible.
- **Execution:** per-unit seeds are HMAC-derived, and the deletion-matched control uses a domain-separated stream. The engineering simulation is deterministic: 110 of 110 shared units and 48 of 48 witnesses are identical between V1.7.2 and V1.8.
- **Manuscript:** byte-identical rebuilds are claimed only under the recorded toolchain:
  - Ubuntu 24.04.4;
  - pdfTeX 1.40.25 (TeX Live 2023), BibTeX 0.99d, acmart v2.03, hyperref 7.01h;
  - Python 3.12.3, Poppler 24.02.0;
  - `LC_ALL=LANG=C.UTF-8` and `TZ=UTC`, set explicitly by the build script; `SOURCE_DATE_EPOCH=1767225600`.

  No cross-toolchain byte identity is claimed. The manuscript build package is kept outside this review repository because it also builds a clearly marked hypothetical ceiling draft, which does not belong in a review artifact.
