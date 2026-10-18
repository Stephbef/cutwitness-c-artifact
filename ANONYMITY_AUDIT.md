# Anonymity audit

**Scope:** every file in the repository, including binary members such as wheels, and the PDF metadata.

**Patterns searched:**
- workstation paths (`/home/…`, `/Users/…`);
- email addresses;
- secret tokens (AWS, GitHub, private keys, Slack);
- assistant or vendor names;
- compiled Python files, git directories and shell histories.

**Findings:**
- Real leaks: **0** 
- Generated or history files: **0**; the 64 `.pyc` files present in the earlier repository were removed.
- Intentional patterns (security-scanner rules and tests, this checker, third-party vendored metadata), 5:
  - scripts/submission_readiness.py: assistant or vendor name
  - artifact/authoritative_v1_8/cutwitness/security.py: assistant or vendor name
  - artifact/authoritative_v1_8/tests/test_security.py: workstation path
  - artifact/authoritative_v1_8/tests/test_security.py: secret token
  - artifact/authoritative_v1_8/vendor/wheels/duckdb-1.1.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl: email [third-party vendored package metadata]

**PDF metadata:** no Author field. The title is the paper title; Creator and Producer name only acmart and pdfTeX. The manuscript reads "Anonymous Author(s)".

**Git:** no `.git` directory and no remotes.
