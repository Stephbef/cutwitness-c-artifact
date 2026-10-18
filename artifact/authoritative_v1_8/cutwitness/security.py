"""Secret and privacy scanner (package tree, run outputs). Used by tests, by run_one_shot.sh and before packaging."""
from __future__ import annotations
import os, re, sys
from typing import List

PATTERNS = {
    "jwt": re.compile(rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"),
    "aws_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(rb"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    "slack_token": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "refresh_token_value": re.compile(rb'refresh_token"\s*:\s*"[^"{}\s]{8,}"'),
    "bearer_value": re.compile(rb"Bearer [A-Za-z0-9._-]{20,}"),
    "registry_auth": re.compile(rb'"auths"\s*:'),
}
PRIVATE_PATHS = [re.compile(rb"/home/(?!claude/cw\b)[a-z][a-z0-9_-]+/"), re.compile(rb"/Users/[A-Za-z0-9_-]+/"),
                 re.compile(rb"/home/claude"), re.compile(rb"/mnt/user-data"), re.compile(rb"/root/")]
FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519", ".netrc", ".pypirc", "credentials", "config.json", ".bash_history",
                   ".zsh_history", ".python_history", ".psql_history", ".DS_Store"}
FORBIDDEN_SUFFIX = (".pem", ".key", ".p12", ".pfx", ".swp", ".swo", "~", ".orig", ".rej", ".bak", ".tmp")
FORBIDDEN_DIRS = ("raw_redistributable",)   # raw W1 feeds are never packaged (licence classes apply to run outputs only)
SKIP_DIRS = {".git", "__pycache__", ".venv", ".pytest_cache"}
BINARY_SUFFIX = (".whl", ".zip", ".gz", ".pyc")
ALLOW = {  # explicit, reviewed exceptions (scanner source itself; documented non-secret fixed local DB password)
    "cutwitness/security.py": {"private_paths", "bearer_value", "refresh_token_value", "registry_auth"},
    "tests/test_security.py": {"private_paths", "jwt", "bearer_value", "private_key", "refresh_token_value"},
    "cutwitness/w1.py": {"bearer_value"},
}


def scan(root: str, extra_secrets: List[str] = ()) -> List[dict]:
    findings = []
    env_tok = [os.environ.get(k) for k in ("CUTWITNESS_W1_TOKEN", "MOBILITY_DB_TOKEN") if os.environ.get(k)]
    secrets = [s.encode() for s in list(extra_secrets) + env_tok if s]
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            p = os.path.join(d, f); rel = os.path.relpath(p, root).replace(os.sep, "/")
            if f in FORBIDDEN_NAMES or f.endswith(FORBIDDEN_SUFFIX) or ".tmp." in f:
                findings.append({"file": rel, "kind": "forbidden_file"})
            if any(part in FORBIDDEN_DIRS for part in rel.split("/")) or (f.endswith(".zip") and "gtfs" in rel.lower()):
                findings.append({"file": rel, "kind": "raw_test_data"})
            if f.endswith(BINARY_SUFFIX):
                continue
            data = open(p, "rb").read()
            allow = ALLOW.get(rel, set())
            for k, rx in PATTERNS.items():
                if k not in allow and rx.search(data):
                    findings.append({"file": rel, "kind": k})
            if "private_paths" not in allow and any(rx.search(data) for rx in PRIVATE_PATHS):
                findings.append({"file": rel, "kind": "private_path"})
            for s in secrets:
                if s in data:
                    findings.append({"file": rel, "kind": "configured_secret_value"})
    return findings


def dockerfile_findings(root: str) -> List[dict]:
    out = []
    for d, _, files in os.walk(root):
        for f in files:
            if f == "Dockerfile":
                txt = open(os.path.join(d, f)).read()
                for ln in txt.splitlines():
                    if re.match(r"\s*(ENV|ARG)\s+\S*(TOKEN|SECRET|PASSWORD|KEY)\S*", ln, re.I):
                        out.append({"file": os.path.relpath(os.path.join(d, f), root), "kind": "secret_in_docker_layer", "line": ln.strip()})
    return out


def main(argv=None) -> int:
    root = (argv or sys.argv[1:] or ["."])[0]
    f = scan(root) + dockerfile_findings(root)
    for x in f:
        print("SECURITY_FINDING", x)
    print("SECURITY_SCAN", "PASS" if not f else "FAIL", len(f))
    return 0 if not f else 4


if __name__ == "__main__":
    sys.exit(main())
