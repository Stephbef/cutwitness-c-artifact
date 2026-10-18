#!/usr/bin/env python3
"""Fail-closed submission-readiness check (stdlib only). Exit 0 only if the authoritative package verifies, the anonymity
scan finds no real leak, and a sealed observed-results bundle (results/FINAL_VERDICT.json) is present."""
import json, os, re, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); ART = os.path.join(ROOT, "artifact", "authoritative_v1_8")
PAT = {"workstation path": r"/home/[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/", "email": r"[\w.+-]+@[\w-]+\.(com|org|edu|net|io|de|fr|uk|ch)\b",
       "secret token": r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[bp]-[A-Za-z0-9-]+",
       "assistant or vendor name": r"\b(claude|anthropic)\b"}
THIRD_PARTY = ("artifact/authoritative_v1_8/vendor/wheels/",)
INTENTIONAL = {"artifact/authoritative_v1_8/cutwitness/security.py", "artifact/authoritative_v1_8/tests/test_security.py", "scripts/submission_readiness.py",
               "ANONYMITY_AUDIT.md", "ANONYMITY.md"}
def scan():
    hits, intentional, bad_files = [], [], []
    for d, ds, fs in os.walk(ROOT):
        ds[:] = [x for x in ds if x != ".git"] ; bad_files += [os.path.join(d, x) for x in ds if x in ("__pycache__", ".git")]
        for f in fs:
            p = os.path.join(d, f); rel = os.path.relpath(p, ROOT)
            if f.endswith((".pyc", ".pyo")) or f in (".bash_history", ".zsh_history", ".python_history"): bad_files.append(rel); continue
            try: s = open(p, "rb").read().decode("utf-8", "ignore")
            except Exception: continue
            for name, pat in PAT.items():
                if re.search(pat, s, re.I if name.startswith("assistant") else 0):
                    (intentional if rel in INTENTIONAL or rel.startswith(THIRD_PARTY) else hits).append(f"{rel}: {name}" + (" [third-party vendored package metadata]" if rel.startswith(THIRD_PARTY) else ""))
    return hits, intentional, bad_files
def main():
    st = {}
    v = subprocess.run([sys.executable, "tools/verify_package.py"], cwd=ART, capture_output=True, text=True)
    st["authoritative_package_integrity"] = {"ok": "PACKAGE_VERIFY PASS" in v.stdout, "detail": v.stdout.strip().splitlines()[-1] if v.stdout.strip() else v.stderr[-200:]}
    hits, intentional, bad = scan()
    st["anonymity_scan"] = {"ok": not hits and not bad, "real_leaks": hits, "generated_or_history_files": bad, "intentional_patterns": intentional}
    fv = os.path.join(ROOT, "results", "FINAL_VERDICT.json")
    st["observed_result_bundle_present"] = {"ok": os.path.exists(fv), "detail": "present" if os.path.exists(fv) else "no results/FINAL_VERDICT.json: real campaign not executed"}
    st["submission_support_ready"] = all(x["ok"] for x in st.values() if isinstance(x, dict))
    json.dump(st, open(os.path.join(ROOT, "SUBMISSION_READINESS_STATUS.json"), "w"), indent=1, sort_keys=True)
    print(json.dumps(st, indent=1, sort_keys=True)); return 0 if st["submission_support_ready"] else 1
if __name__ == "__main__":
    sys.exit(main())
