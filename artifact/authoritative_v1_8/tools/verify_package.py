"""Stdlib-only package verifier: every file listed in manifests/PREEXECUTION_MANIFEST.json must match its SHA-256,
and no unlisted file may exist outside runtime directories."""
import hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME = (".venv/", "runs/", "__pycache__/", ".pytest_cache/")


def main(root: str = None) -> int:
    ROOT_ = root or ROOT
    mp = os.path.join(ROOT_, "manifests", "PREEXECUTION_MANIFEST.json")
    if not os.path.exists(mp):
        print("PACKAGE_VERIFY FAIL manifest missing"); return 2
    man = json.load(open(mp)); listed = {}
    bad = []
    for e in man["files"]:
        p = os.path.join(ROOT_, e["path"]); listed[e["path"]] = 1
        if not os.path.exists(p) or hashlib.sha256(open(p, "rb").read()).hexdigest() != e["sha256"] or os.path.getsize(p) != e["bytes"]:
            bad.append(e["path"])
    extra = []
    for d, dirs, fs in os.walk(ROOT_):
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), ROOT_).replace(os.sep, "/")
            if rel in listed or rel in ("manifests/PREEXECUTION_MANIFEST.json", "SHA256SUMS") or any(r in rel + "/" or rel.startswith(r) for r in RUNTIME) or rel.endswith(".pyc"):
                continue
            extra.append(rel)
    ok = not bad and not extra
    print("PACKAGE_VERIFY", "PASS" if ok else "FAIL", "files", len(listed), "mismatched", bad[:10], "unlisted", extra[:10])
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
