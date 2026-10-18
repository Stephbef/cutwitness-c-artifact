"""Derive pins, lock report, amendment record, matrix, preflight report and simulation evidence from the repository."""
import ast, collections, datetime, hashlib, json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from cutwitness.campaign import Journal
from cutwitness.config import digest, load
from cutwitness.matrix import build_matrix, legacy_v1_0_slot_hours, to_csv
from cutwitness.model import sha
from cutwitness.preflight import duration_preflight, measure, report_text

git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
h = lambda p: hashlib.sha256(open(os.path.join(ROOT, p), "rb").read()).hexdigest()
LABEL = "ENGINEERING VALIDATION ONLY \u2014 NOT SCIENTIFIC RESULTS"
SRR = "SERVER_RESOLUTION_REQUIRED"
CFG = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))
PINS = {"postgresql": {"version": "17.10", "tag": "REL_17_10", "commit": "25c49f3a4a742ba283f5cc43cc7f1d361552e917",
                       "base_image": "postgres:17.10-bookworm", "base_image_digest": SRR},
        "pg_ivm": {"version": "1.16", "tag": "v1.16", "commit": "22b4b4520a3d2be896f07d3d55fb34772a5ecf8e",
                   "image": "cutwitness/pg_ivm:frozen (built from server/targets/pgivm/Dockerfile)", "image_id": SRR},
        "risingwave": {"version": "3.1.0", "tag": "v3.1.0", "commit": "45baf6460ea942e4ff57a5aa057d5b8db7f3b563",
                       "image": "risingwavelabs/risingwave:v3.1.0", "image_digest": SRR},
        "feldera": {"version": "0.366.0", "tag": "v0.366.0", "commit": "4532aa1007e370ed4440527e39eebb76931896bc",
                    "image": "ghcr.io/feldera/pipeline-manager:0.366.0", "image_digest": SRR},
        "duckdb": {"version": "1.1.3", "role": "O3 independent reference"},
        "psycopg": {"version": "3.2.10", "role": "PostgreSQL wire protocol (pg_ivm, RisingWave)"}}


def wheels():
    out = {}
    for ln in open(os.path.join(ROOT, "vendor", "WHEEL_SHA256SUMS")).read().splitlines():
        hh, name = ln.split()
        assert hashlib.sha256(open(os.path.join(ROOT, "vendor", "wheels", name), "rb").read()).hexdigest() == hh, name
        out[name] = hh
    return out


def pins():
    w = wheels()
    freeze = {"schema_version": "target-freeze/2", "status": "PINNED_SOURCE_IDENTITIES; image digests resolved and journaled at server stage S2",
              "targets": PINS, "upgrade": "UPGRADE excluded on all targets (Amendment v1.1 preserved the earlier freeze)",
              "python_wheels_sha256": w,
              "note": "Commits were taken from the projects' signed git tags via git ls-remote. Image digests cannot be resolved without a container "
                      "runtime; the controller pulls/builds once at S2, journals the digests, and refuses to resume if any digest changes. "
                      "The pg_ivm base-image digest is not journaled separately; the built image ID is."}
    json.dump(freeze, open(os.path.join(ROOT, "manifests", "TARGET_VERSION_FREEZE.json"), "w"), indent=1, sort_keys=True)
    L = ["# VERSION_PINS", "", "| Component | Version | Source identity (tag @ commit) | Image | Digest status |", "|---|---|---|---|---|"]
    for k in ("postgresql", "pg_ivm", "risingwave", "feldera"):
        p = PINS[k]; img = p.get("image") or p.get("base_image")
        L.append(f"| {k} | {p['version']} | {p['tag']} @ `{p['commit']}` | `{img}` | {SRR} (journaled at S2) |")
    L += ["| DuckDB | 1.1.3 | PyPI wheel | — | wheel hash pinned |", "| psycopg / psycopg-binary | 3.2.10 | PyPI wheels | — | wheel hashes pinned |", "",
          "## Vendored wheels (SHA-256)", ""] + [f"- `{n}` `{x}`" for n, x in sorted(w.items())]
    L += ["", "UPGRADE is excluded on all targets. Python 3.12 on Linux x86_64 is required by the wheelhouse."]
    open(os.path.join(ROOT, "VERSION_PINS.md"), "w").write("\n".join(L) + "\n")


def lockreport():
    std = set(sys.stdlib_module_names); third = collections.defaultdict(set)
    for d, _, fs in os.walk(os.path.join(ROOT, "cutwitness")):
        for f in fs:
            if f.endswith(".py"):
                tree = ast.parse(open(os.path.join(d, f)).read())
                for n in ast.walk(tree):
                    mods = [a.name for a in n.names] if isinstance(n, ast.Import) else ([n.module] if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module else [])
                    for m in mods:
                        top = m.split(".")[0]
                        if top not in std and top != "cutwitness":
                            third[top].add(os.path.relpath(os.path.join(d, f), ROOT))
    lock = [l for l in open(os.path.join(ROOT, "vendor", "requirements.lock")).read().splitlines() if l and not l.startswith("#")]
    qa = [l for l in open(os.path.join(ROOT, "vendor", "requirements-qa.lock")).read().splitlines() if l and not l.startswith("#")]
    L = ["# Dependency lock report (generated)", "", "## Third-party imports in active source", ""]
    L += [f"- `{m}` — used by {', '.join(sorted(v))}" for m, v in sorted(third.items())]
    L += ["", "No other third-party module is imported by `cutwitness/` (numpy and scipy are not dependencies; statistics are stdlib-only and "
          "verified against a frozen scipy reference fixture).", "", "## Runtime lock (`vendor/requirements.lock`, installed offline with `--no-index --require-hashes`)", ""]
    L += [f"- `{l}`" for l in lock] + ["", "## QA lock (`vendor/requirements-qa.lock`, tests only)", ""] + [f"- `{l}`" for l in qa]
    L += ["", "## Bootstrap", "", "- `pip-24.2-py3-none-any.whl` (vendored; executed directly from the wheel inside a `--without-pip` venv)", "",
          "Clean offline installation into a fresh venv from the wheelhouse is exercised by `tests/test_packaging.py` (wrapper) and by the fresh-extraction verification."]
    assert set(third) <= {"duckdb", "psycopg"}, third
    open(os.path.join(ROOT, "manifests", "DEPENDENCY_LOCK_REPORT.md"), "w").write("\n".join(L) + "\n")


def leaf_diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            out += leaf_diff(a.get(k, "<absent>"), b.get(k, "<absent>"), f"{path}.{k}" if path else k)
    elif a != b:
        out.append({"path": path, "before": a, "after": b})
    return out


def amendment():
    pre_full = git("rev-parse", "a859cc3"); post_full = git("rev-parse", "ab065a9")
    cfg_pre = json.loads(git("show", "a859cc3:campaign/FROZEN_CAMPAIGN.yaml")); cfg_post = json.loads(git("show", "ab065a9:campaign/FROZEN_CAMPAIGN.yaml"))
    sci_paths = ("full.budget", "matrix", "duration_gate", "amendments", "resources")
    diff = [d for d in leaf_diff(cfg_pre, cfg_post) if not d["path"].startswith("code_tree_digest")]
    rec = {"amendment_path": "CUTWITNESS_C_PREEXECUTION_FEASIBILITY_AMENDMENT_v1_1.md (identical copy at science/)",
           "amendment_sha256": h("science/CUTWITNESS_C_PREEXECUTION_FEASIBILITY_AMENDMENT_v1_1.md"),
           "pre_amendment_commit": pre_full, "post_amendment_commit": post_full,
           "pre_amendment_config_digest": sha(cfg_pre), "post_amendment_config_digest": sha(cfg_post),
           "final_packaged_config_digest": digest(CFG),
           "final_vs_post_amendment_config_differences": [d["path"] for d in leaf_diff(cfg_post, CFG)],
           "exact_parameter_diff_pre_to_post": diff,
           "scientific_parameter_changes": [d for d in diff if d["path"].startswith(sci_paths)],
           "justification": "Prospective feasibility correction: the v1.0 matrix projected ~253 days on 4 slots. Changed before any real observation.",
           "no_real_test_observation_before_amendment": True,
           "unchanged": ["10 stochastic repetitions", "all baseline families", "pilot tools, 12 h budget and A-D thresholds", "targets", "workloads",
                         "seeds and HMAC derivation", "RQ1-RQ5", "bug accounting", "right-censoring of zero-bug runs", "VALIDATION/TEST firewall"],
           "upgrade": "excluded on all three targets (unchanged)",
           "duration_gate": "max_campaign_days = 45, measured slots, fail closed, no bypass flag",
           "record_generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "record_note": "Later config digests differ from the post-amendment digest only in operational fields listed above "
                          "(code-tree digest after fixes, SEALED release state, pg_ivm server command); no scientific parameter changed after the amendment."}
    later = [p for p in rec["final_vs_post_amendment_config_differences"] if p.startswith(("full.", "pilot.", "matrix.", "duration_gate.", "workloads.", "targets.") )
             and not p.startswith(("targets.pg_ivm.command",))]
    rec["scientific_changes_after_amendment"] = later
    json.dump(rec, open(os.path.join(ROOT, "AMENDMENT_v1_1_RECORD.json"), "w"), indent=1, sort_keys=True, default=str)
    print("amendment pre", rec["pre_amendment_config_digest"][:12], "post", rec["post_amendment_config_digest"][:12], "later-sci", later)


def matrix():
    open(os.path.join(ROOT, "CAMPAIGN_MATRIX.csv"), "w").write(to_csv(build_matrix(CFG)))
    G = 2 ** 30
    parts = ["# CAMPAIGN_PREFLIGHT_REPORT (generated). The authoritative preflight runs on the server at S2 with measured resources.", ""]
    for name, meas in (("MEASURED: this build environment", None),
                       ("PLANNING: reference server 64 vCPU / 256 GiB / 2 TiB", {"AVAILABLE_VCPUS": 64, "AVAILABLE_RAM_BYTES": 256 * G, "AVAILABLE_DISK_BYTES": 2048 * G}),
                       ("PLANNING: 26 vCPU host (3 CPU slots)", {"AVAILABLE_VCPUS": 26, "AVAILABLE_RAM_BYTES": 256 * G, "AVAILABLE_DISK_BYTES": 2048 * G})):
        p = duration_preflight(CFG, meas if meas else measure(ROOT))
        parts += [f"## {name}", report_text(p), ""]
    open(os.path.join(ROOT, "CAMPAIGN_PREFLIGHT_REPORT.txt"), "w").write("\n".join(parts))


def simulation(run_dir):
    from cutwitness.controller import plan_units
    from cutwitness.config import load as L
    cfg = L(os.path.join(ROOT, "campaign", "ENGINEERING_SIMULATION.yaml"))
    v = json.load(open(os.path.join(run_dir, "FINAL_VERDICT.json"))); j = Journal(os.path.join(run_dir, "journal.jsonl"))
    st = collections.Counter(r["payload"]["status"] for r in j.recs if r["kind"] == "UNIT")
    commits = collections.Counter(r["payload"]["unit_id"] for r in j.recs if r["kind"] == "UNIT" and r["payload"]["status"] == "COMMITTED")
    planned = plan_units(cfg, "pilot") + plan_units(cfg, "full") + plan_units(cfg, "closure")
    exe = [u for u in planned if u["unit_class"] != "NOT_APPLICABLE"]; na = [u for u in planned if u["unit_class"] == "NOT_APPLICABLE"]
    stages = {r["payload"]["stage"]: r["payload"] for r in j.recs if r["kind"] == "STAGE_DONE"}
    res = {}
    for r in j.recs:
        if r["kind"] == "UNIT" and r["payload"]["status"] == "COMMITTED":
            res[r["payload"]["unit_id"]] = json.load(open(os.path.join(run_dir, "results", r["payload"]["result"] + ".json")))
    cands = collections.Counter(u["target"] for u in res.values() for d in u.get("divergences", []) if d.get("triage", {}).get("candidate"))
    tlp = [u for k, u in res.items() if "baseline_tlp" in k]
    ev = {"label": LABEL, "config_digest": digest(cfg), "verdict": v["verdict"], "results_digest": v["results_digest"],
          "stages_completed": sorted(stages), "planned_executable_units": len(exe), "committed_units": len(commits),
          "all_executable_committed": set(u["unit_id"] for u in exe) <= set(commits), "duplicate_commits": max(commits.values()) > 1,
          "not_applicable_units_journaled": st.get("NOT_APPLICABLE", 0), "not_applicable_planned": len(na),
          "failed_operational": st.get("FAILED_OPERATIONAL", 0), "pilot_decision": stages["S6"]["decision"],
          "S5_tester_conformance": stages["S5"], "seeded_fault_by_sim_target": {t: cfg["targets"][t]["fault"] for t in cfg["targets"]},
          "candidates_by_sim_target": dict(cands), "correct_sim_target_candidates": cands.get("risingwave", 0),
          "tlp_secondary_units_committed": len(tlp), "journal_head": v["journal_head"],
          "latent_attribution_by_class": stages["S8"].get("latent_attribution", {}),
          "note": "Simulated targets run the toy engine behind each real target's frozen capability matrix. Nothing here is a result about pg_ivm, Feldera or RisingWave."}
    json.dump(ev, open(os.path.join(ROOT, "qa", "SIMULATION_EVIDENCE.json"), "w"), indent=1, sort_keys=True, ensure_ascii=False)
    print({k: ev[k] for k in ("verdict", "all_executable_committed", "duplicate_commits", "not_applicable_units_journaled", "failed_operational",
                              "correct_sim_target_candidates", "tlp_secondary_units_committed", "pilot_decision")}, ev["S5_tester_conformance"]["ok"])


if __name__ == "__main__":
    pins(); lockreport(); amendment(); matrix()
    if len(sys.argv) > 1:
        simulation(sys.argv[1])
