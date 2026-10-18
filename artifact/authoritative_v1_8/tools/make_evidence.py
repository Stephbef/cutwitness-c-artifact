"""Regenerate qa/ evidence from the frozen code state. Usage: make_evidence.py crash|provenance|mocks|qa"""
import collections, json, os, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
QA = os.path.join(ROOT, "qa")
LABEL = "ENGINEERING VALIDATION ONLY \u2014 NOT SCIENTIFIC RESULTS"


def dump(name, obj):
    json.dump(obj, open(os.path.join(QA, name), "w"), indent=1, sort_keys=True, ensure_ascii=False)


def crash():
    import tempfile
    from test_crash_matrix import POINTS, material, run
    from cutwitness.campaign import Journal
    base = tempfile.mkdtemp(prefix="cwcrash-"); ref = os.path.join(base, "ref")
    assert run(ref) == 0
    rv = json.load(open(os.path.join(ref, "FINAL_VERDICT.json"))); rows = []
    for p in POINTS:
        d = os.path.join(base, p); rc1 = run(d, p); rid = json.load(open(os.path.join(d, "run_meta.json")))["run_id"]
        rc2 = run(d); v = json.load(open(os.path.join(d, "FINAL_VERDICT.json"))); j = Journal(os.path.join(d, "journal.jsonl"))
        commits = collections.Counter(r["payload"]["unit_id"] for r in j.recs if r["kind"] == "UNIT" and r["payload"]["status"] == "COMMITTED")
        seeds = collections.defaultdict(set)
        for r in j.recs:
            if r["kind"] == "UNIT" and r["payload"]["status"] == "RUNNING":
                seeds[r["payload"]["unit_id"]].add(r["payload"]["seed"])
        rows.append({"crash_point": p, "crash_exit_code": rc1, "crash_occurred": rc1 == 77, "resume_exit_code": rc2,
                     "torn_tail_recovered": any(r["kind"] == "TORN_TAIL_RECOVERED" for r in j.recs), "journal_chain_valid": j.verify()[0],
                     "max_commits_per_unit": max(commits.values()), "seeds_unchanged": all(len(s) == 1 for s in seeds.values()),
                     "run_id_unchanged": v.get("run_id") == rid, "material_outputs_identical": material(d) == material(ref),
                     "final_results_digest": v.get("results_digest"), "digest_equal": v.get("results_digest") == rv["results_digest"],
                     "verdict": v["verdict"]})
    ok = all(r["crash_occurred"] and r["resume_exit_code"] == 0 and r["digest_equal"] and r["material_outputs_identical"] and
             r["max_commits_per_unit"] == 1 and r["seeds_unchanged"] and r["run_id_unchanged"] and r["journal_chain_valid"] for r in rows)
    dump("CRASH_MATRIX.json", {"label": LABEL, "config": "campaign/CRASHTEST_SIMULATION.yaml", "reference_verdict": rv["verdict"],
                               "reference_results_digest": rv["results_digest"], "points": rows, "all_pass": ok})
    lines = [f"# Crash/resume matrix ({LABEL})", "", f"Reference: {rv['verdict']}, FINAL_RESULTS_DIGEST {rv['results_digest']}", "",
             "| Crash point | Crash | Torn tail | Resume | Digest equal | Material identical | Max commits/unit | Seeds | run_id |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['crash_point']} | {r['crash_occurred']} | {r['torn_tail_recovered']} | {r['resume_exit_code']} | {r['digest_equal']} | "
                     f"{r['material_outputs_identical']} | {r['max_commits_per_unit']} | {r['seeds_unchanged']} | {r['run_id_unchanged']} |")
    lines += ["", f"ALL POINTS PASS: {ok}"]
    open(os.path.join(QA, "CRASH_MATRIX.md"), "w").write("\n".join(lines) + "\n")
    print("crash matrix all_pass", ok)


def provenance():
    """Reconstruct the earlier Feldera seed-14 event: same mocks, same seed, pre-fix parser emulated."""
    import random
    from decimal import Decimal
    from conftest import mock_sessions
    from cutwitness.adapters import feldera as F
    from cutwitness.conformance import run_conformance
    from cutwitness.model import src
    from cutwitness.oracles import duckdb_obs, obs_digest, reference_obs
    from cutwitness.w3 import gen_history
    out = {"classification": "MOCK_CONFORMANCE", "target": "feldera (protocol mock: cutwitness.adapters.mocks.MockFeldera, DuckDB-backed)",
           "adapter": "cutwitness.adapters.feldera.FelderaAdapter", "real_target_identity": None, "seed": 14}
    cur = F._parse
    F._parse = lambda v: Decimal(repr(v)) if isinstance(v, float) else cur(v)          # pre-fix behaviour (float -> Decimal)
    try:
        m = mock_sessions(14); s, vs = m["schema"], m["views"]
        r_pre = run_conformance(m["fe"][0], s, vs, {"version": "0.366.0"}, 14, evidence_kind="PROTOCOL_MOCK")
        m = mock_sessions(14); a = m["fe"][0]("prov"); h = gen_history(random.Random(14), s, 6)
        for t in h:
            a.apply_transaction(t)
        x = src(s, h); inc = a.read_views(); cr = a.clean_rebuild(x); ref = reference_obs(vs, x); o3 = duckdb_obs(s, vs, x)
        diff = {v.name: {"engine_only": [[repr(c) for c in r] for r, mm in (inc[v.name] - ref[v.name]).items_sorted() if mm > 0],
                         "reference_only": [[repr(c) for c in r] for r, mm in (ref[v.name] - inc[v.name]).items_sorted() if mm > 0]}
                for v in vs if inc[v.name].digest() != ref[v.name].digest()}
        out.update({"pre_fix_failed_checks": [c["check"] for c in r_pre["checks"] if not c["ok"]], "differing_views": sorted(diff),
                    "differing_rows": diff, "incremental_equals_clean_rebuild": obs_digest(inc) == obs_digest(cr),
                    "reference_equals_duckdb_O3": obs_digest(ref) == obs_digest(o3)})
    finally:
        F._parse = cur
    m = mock_sessions(14)
    r_now = run_conformance(m["fe"][0], m["schema"], m["views"], {"version": "0.366.0"}, 14, evidence_kind="PROTOCOL_MOCK")
    fix = subprocess.run(["git", "log", "--format=%H %s", "-S", "JSON floats stay binary", "--", "cutwitness/adapters/feldera.py"],
                         cwd=ROOT, capture_output=True, text=True).stdout.strip().splitlines()
    out.update({"root_cause": "adapter defect: FelderaAdapter._parse converted a JSON binary AVG (DuckDB DOUBLE in the mock) to Decimal, so the "
                              "binary-AVG tolerance rule was skipped and a correct AVG was canonicalized as AVG_MISMATCH",
                "reference_or_duckdb_wrong": False, "fixed": r_now["ok"], "post_fix_checks_ok": r_now["ok"],
                "fix_commit": fix[-1] if fix else "not found in git history",
                "regression_tests": ["tests/test_regressions.py::test_regression_2_avg_canonicalization_and_exact_types",
                                     "qa/MOCK_CONFORMANCE.json (seed 14 included in the 30-seed sweep)"],
                "counts_toward_real_target_gate": False,
                "note": "Protocol-mock evidence only. No real Feldera, pg_ivm or RisingWave has been executed in this environment."})
    dump("CONFORMANCE_PROVENANCE.json", out); print("provenance", out["classification"], out["pre_fix_failed_checks"], "fixed", out["fixed"])


def mocks():
    from conftest import mock_sessions
    from cutwitness.conformance import run_conformance
    rows = []
    for seed in range(1, 31):
        m = mock_sessions(seed)
        for nm, mk, vs, pin in (("pg_ivm", m["pg"][0], m["pg_views"], {"server_version_num": "170010"}),
                                ("risingwave", m["rw"][0], m["views"], {"version": "3.1.0"}),
                                ("feldera", m["fe"][0], m["views"], {"version": "0.366.0"})):
            r = run_conformance(mk, m["schema"], vs, pin, seed, evidence_kind="PROTOCOL_MOCK")
            rows.append({"seed": seed, "target": nm, "ok": r["ok"], "checks": len(r["checks"]), "failed": [c["check"] for c in r["checks"] if not c["ok"]]})
    dump("MOCK_CONFORMANCE.json", {"evidence_kind": "PROTOCOL_MOCK", "counts_toward_real_target_gate": False, "runs": len(rows),
                                   "passed": sum(r["ok"] for r in rows), "rows": rows})
    print("mock conformance", sum(r["ok"] for r in rows), "/", len(rows))


def qa():
    r = subprocess.run([sys.executable, os.path.join("qa", "run_internal_qa.py")], cwd=ROOT, capture_output=True, text=True)
    print(r.stdout[-300:], r.returncode)


if __name__ == "__main__":
    {"crash": crash, "provenance": provenance, "mocks": mocks, "qa": qa}[sys.argv[1]]()
