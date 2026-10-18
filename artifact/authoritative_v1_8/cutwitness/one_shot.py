"""Single entry point. Real campaign runs only from a SEALED package; otherwise fails closed before S1."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, shutil, sys
from .model import cjson, sha

VERDICTS = ("COMPLETE_PILOT_NO_GO", "COMPLETE_FULL_CAMPAIGN", "NOT_STARTED_OPERATIONAL", "CAPABILITY_BLOCKED",
            "CONFORMANCE_BLOCKED", "INCOMPLETE_OPERATIONAL_RESUMABLE", "INCOMPLETE_NONRESUMABLE_CORRUPTION")
REAL_ADAPTERS = {}  # pg_ivm / feldera / risingwave adapters are not part of this package (see PREEXECUTION_CLOSURE_REPORT)


def pkg_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def verify_package(root: str) -> dict:
    mp = os.path.join(root, "manifests", "PREEXECUTION_MANIFEST.json")
    if not os.path.exists(mp):
        return {"ok": False, "reason": "manifest missing"}
    man = json.load(open(mp)); bad = []
    for e in man["files"]:
        p = os.path.join(root, e["path"])
        if not os.path.exists(p) or hashlib.sha256(open(p, "rb").read()).hexdigest() != e["sha256"]:
            bad.append(e["path"])
    return {"ok": not bad, "checked": len(man["files"]), "mismatched": bad[:20]}


def fingerprint() -> dict:
    """S1 host facts for the paper's server table (observed, never assumed)."""
    import subprocess
    cpu_model = None
    try:
        for ln in open("/proc/cpuinfo"):
            if ln.lower().startswith("model name"):
                cpu_model = ln.split(":", 1)[1].strip(); break
    except OSError:
        pass
    try:
        ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError):
        ram = None
    docker_version = None
    if shutil.which("docker"):
        try:
            docker_version = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True,
                                            text=True, timeout=30).stdout.strip() or None
        except (OSError, subprocess.TimeoutExpired):
            docker_version = None
    st = shutil.disk_usage(".")
    return {"os": platform.platform(), "kernel": platform.release(), "python": platform.python_version(), "cpus": os.cpu_count(),
            "cpu_model": cpu_model, "ram_bytes": ram, "disk_free_bytes": st.free, "docker_server_version": docker_version,
            "container_runtime": [c for c in ("docker", "podman") if shutil.which(c)]}


def preflight(cfg: dict) -> dict:
    st = os.statvfs(".")
    free_gb = st.f_bavail * st.f_frsize / 2**30
    try:
        mem_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except (ValueError, OSError):
        mem_gb = 0.0
    need = cfg.get("server_requirements", {})
    checks = {"disk_gb": (free_gb, need.get("disk_gb", 0)), "ram_gb": (mem_gb, need.get("ram_gb", 0)),
              "cpus": (os.cpu_count() or 0, need.get("cpus", 0))}
    res = {k: {"have": round(v[0], 1), "need": v[1], "ok": v[0] >= v[1]} for k, v in checks.items()}
    res["container_runtime"] = {"ok": bool(fingerprint()["container_runtime"])}
    res["w1_token_present"] = {"ok": bool(os.environ.get(cfg.get("w1_token_env", "CUTWITNESS_W1_TOKEN")))}
    res["all_ok"] = all(v["ok"] for v in res.values() if isinstance(v, dict))
    return res


def final(out_dir: str, verdict: str, reason: str) -> int:
    assert verdict in VERDICTS
    os.makedirs(out_dir, exist_ok=True)
    from .campaign import atomic_write
    atomic_write(os.path.join(out_dir, "FINAL_VERDICT.json"), cjson({"verdict": verdict, "reason": reason}).encode())
    print(cjson({"verdict": verdict, "reason": reason}))
    return 0 if verdict.startswith("COMPLETE") else 3


def campaign_legacy_guard(cfg: dict, run_dir: str) -> int:
    root = pkg_root()
    vp = verify_package(root)
    if not vp["ok"]:
        return final(run_dir, "NOT_STARTED_OPERATIONAL", f"S0 package integrity failed: {vp}")
    if cfg.get("release_state") != "SEALED":
        return final(run_dir, "NOT_STARTED_OPERATIONAL",
                     "S0: package release_state is " + str(cfg.get("release_state")) +
                     "; preexecution closure is BLOCKED, no scientific unit may be created")
    pf = preflight(cfg)
    if not pf["all_ok"]:
        return final(run_dir, "NOT_STARTED_OPERATIONAL", f"S2 preflight failed: {pf}")
    missing = [t for t in cfg["full"]["targets"] if t not in REAL_ADAPTERS]
    if missing:
        return final(run_dir, "CAPABILITY_BLOCKED", f"S4: no verified adapter for {missing}")
    return final(run_dir, "INCOMPLETE_NONRESUMABLE_CORRUPTION", "unreachable: sealed package without adapters")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cutwitness.one_shot")
    ap.add_argument("--config", default=os.path.join(pkg_root(), "campaign", "FROZEN_CAMPAIGN.yaml"))
    ap.add_argument("--run-dir", default="runs/cutwitness_c")
    ap.add_argument("--verify-package", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--engineering-dry-run", metavar="OUT")
    a = ap.parse_args(argv)
    if a.verify_package:
        r = verify_package(pkg_root()); print(cjson(r)); return 0 if r["ok"] else 2
    if a.engineering_dry_run:
        from .controller import run
        v = run(os.path.join(pkg_root(), "campaign", "ENGINEERING_SIMULATION.yaml"), a.engineering_dry_run)
        print(cjson(v)); return 0 if v["verdict"].startswith("COMPLETE") else 3
    if a.preflight:
        cfg = json.load(open(a.config)); print(cjson(preflight(cfg))); return 0
    from .controller import run
    v = run(a.config, a.run_dir)
    print(cjson(v))
    return 0 if v["verdict"].startswith("COMPLETE") else 3


if __name__ == "__main__":
    sys.exit(main())
