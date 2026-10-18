"""One-shot controller S0-S12. Identical orchestration for ENGINEERING_SIMULATION and SEALED_CAMPAIGN."""
from __future__ import annotations
import hashlib, json, os, platform, random, shutil, sys
from typing import Dict, List
from . import w1, w2, w3
from .analysis import analyze
from .baselines import ddmin
from .campaign import Campaign, JournalCorruption, atomic_write, hmac_seed, run_units_parallel
from .config import ConfigError, load as load_config
from .conformance import run_conformance
from .crash import crash_point
from .model import cjson, history_canon, history_digest, history_from_canon, sha, src
from .oracles import judge, minimize, triage
from .pilot import evaluate
from .pipeline import run_trial
from .serialize import schema_from_json, views_from_json
from .simtargets import SimSession, applicable_views
from .toyengine import ADVERSARIAL, FAULTS, IN_MODEL, ToyEngine

VERDICTS = ("COMPLETE_PILOT_NO_GO", "COMPLETE_FULL_CAMPAIGN", "NOT_STARTED_OPERATIONAL", "CAPABILITY_BLOCKED",
            "CONFORMANCE_BLOCKED", "INCOMPLETE_OPERATIONAL_RESUMABLE", "INCOMPLETE_NONRESUMABLE_CORRUPTION")
BASELINE_TOOLS = ("baseline_random_clean", "baseline_random_te", "baseline_stateful_fuzz", "baseline_zippy",
                  "baseline_source_por", "baseline_tlp")


class Stop(Exception):
    def __init__(self, verdict, reason):
        super().__init__(reason); self.verdict, self.reason = verdict, reason


def pkg_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def code_digest(root: str) -> str:
    files = {}
    for d, _, fs in os.walk(os.path.join(root, "cutwitness")):
        for f in fs:
            if f.endswith(".py"):
                p = os.path.join(d, f); files[os.path.relpath(p, root)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return sha(sorted(files.items()))


def label_of(cfg) -> str:
    return ("SCIENTIFIC_CAMPAIGN_OUTPUT" if cfg["mode"] == "SEALED_CAMPAIGN"
            else "ENGINEERING VALIDATION ONLY \u2014 NOT SCIENTIFIC RESULTS")


# ------------------------------------------------------------------ S3 datasets
def materialize(cfg: dict, run_dir: str) -> str:
    d = os.path.join(run_dir, "data"); os.makedirs(d, exist_ok=True)
    wc = cfg["workloads"]; ms = cfg["master_seed"]; out = {}
    if "W1" in wc:
        sch = w1.schema()
        if wc["W1"]["source"] == "fixture":
            from .w1fixtures import history as fx
            snaps = [(t, w1.normalize(b, wc["W1"]["sample_routes"], ms)) for t, b in fx()]
            txns = w1.diff_transactions(sch, w1.logical_versions(snaps))
            feeds = {"VALIDATION": [{"feed_id": "FIXTURE-V", "history": history_canon(txns)}],
                     "TEST": [{"feed_id": "FIXTURE-T", "history": history_canon(txns)}]}
        else:
            client = w1.CatalogClient(cfg["w1_token_env"])
            listing = client.get("/v1/gtfs_feeds", {"limit": 5000, "data_type": "gtfs"})
            for f in listing:
                f["n_datasets"] = len(client.get(f"/v1/gtfs_feeds/{f['id']}/datasets", {"limit": 500}))
            val, test = w1.select_regions(listing, ms, wc["W1"]["n_validation"], wc["W1"]["n_test"], wc["W1"]["min_datasets"])
            fw = w1.SplitFirewall(val, test); fw.open_test()
            feeds = {"VALIDATION": [], "TEST": []}
            for split, ids in (("VALIDATION", val), ("TEST", test)):
                for fid in ids:
                    man = w1.materialize_feed(client, fid, fw, wc["W1"]["sample_routes"], ms, wc["W1"]["max_versions"], os.path.join(run_dir, "raw_redistributable"))
                    feeds[split].append({"feed_id": fid, "history": man["history"], "provenance": man["provenance"]})
        out["W1"] = {"schema": sch.to_json(), "feeds": feeds}
    if "W2" in wc:
        sch = w2.schema(); h = w2.refresh_stream(random.Random(hmac_seed(ms, "W2")), sch, wc["W2"]["pairs"], wc["W2"]["sf_units"])
        out["W2"] = {"schema": sch.to_json(), "history": history_canon(h)}
    if "W3" in wc:
        out["W3"] = {"generator": "cutwitness.w3", "txns": wc["W3"]["txns"]}
    blob = cjson(out).encode(); atomic_write(os.path.join(d, "datasets.json"), blob)
    return hashlib.sha256(blob).hexdigest()


def unit_workload(cfg: dict, run_dir: str, u: dict):
    ds = json.load(open(os.path.join(run_dir, "data", "datasets.json")))
    wl = u["workload"]; rng = random.Random(u["seed"])
    if wl == "W3":
        sch = w3.gen_schema(rng); views = w3.gen_views(rng, sch); h = w3.gen_history(rng, sch, ds["W3"]["txns"])
        return sch, views, h
    sch = schema_from_json(ds[wl]["schema"])
    views = (w1.views(sch) if wl == "W1" else w2.views(sch))
    if wl == "W1":
        feeds = ds["W1"]["feeds"]["VALIDATION" if u["phase"] == "pilot" else "TEST"]
        h = history_from_canon(feeds[u["trial"] % len(feeds)]["history"])[: cfg["workloads"]["W1"]["max_txns"]]
    else:
        h = history_from_canon(ds["W2"]["history"])[: cfg["workloads"]["W2"]["max_txns"]]
    return sch, views, h


def make_factory(cfg: dict, target: str, sch, views, slot: int):
    t = cfg["targets"][target]; matrix = cfg["capability_matrix"][target]
    if t["kind"] == "simulated":
        return (lambda: SimSession(sch, views, t["fault"], matrix, t["version"])), \
               {"ops": {k for k, v in matrix["ops"].items() if v == "SUPPORTED"},
                "lifecycle": {k for k, v in matrix["lifecycle"].items() if v == "SUPPORTED"}}
    from .adapters.transport import Docker, Http, PgSql
    from .realtargets import session_factory, slot_port
    make = session_factory(target, t, sch, views, cfg["timeouts"], Docker(), {"sql": PgSql, "http": Http}, slot_port(cfg, target, slot),
                           container_name=f"{t['container']}-s{slot}")
    counter = {"n": 0}

    def fac():
        counter["n"] += 1
        return make(f"cw_s{slot}_{counter['n']}")
    return fac, {"ops": {k for k, v in matrix["ops"].items() if v == "SUPPORTED"},
                 "lifecycle": {k for k, v in matrix["lifecycle"].items() if v == "SUPPORTED"}}


def plan_units(cfg: dict, phase: str) -> List[dict]:
    from .matrix import build_matrix
    out = []
    for r in build_matrix(cfg):
        if r["stage"] == phase:
            out.append({"unit_id": r["unit_id"], "phase": phase, "target": r["target"], "workload": r["workload"], "tool": r["tool"],
                        "trial": r["rep"] if r["rep"] != "-" else 0, "seed": r["seed"], "unit_class": r["unit_class"],
                        "applicability": r["applicability"], "budget": {"kind": r["budget_kind"], "value": r["budget_value"]}})
    return out


def exec_unit(u: dict, slot: int, cfg: dict, run_dir: str) -> dict:
    cls = u.get("unit_class", "SEARCH_TRIAL")
    if cls == "DETERMINISTIC_SUITE":
        return exec_native_suite(u, cfg)
    if cls == "SECONDARY_ORACLE":
        return exec_secondary(u, slot, cfg, run_dir)
    if cls not in ("SEARCH_TRIAL", "ABLATION"):
        raise ValueError(f"unit class {cls} is not executed by exec_unit")
    sch, views, h = unit_workload(cfg, run_dir, u)
    views = applicable_views(views, cfg["capability_matrix"][u["target"]])
    fac, caps = make_factory(cfg, u["target"], sch, views, slot)
    crash_point("during_target_execution")
    b = u["budget"]
    from . import oracles as _orc
    try:
        r = _run_trial_unit(u, fac, caps, sch, views, h, b, cfg)
    finally:
        _orc._REC = None
    r.update({k: u[k] for k in ("unit_id", "phase", "target", "workload", "tool", "trial")})
    r.update({"unit_class": cls, "seed": u["seed"], "schema": sch.to_json(), "views": [v.to_json() for v in views]})
    return r


def _run_trial_unit(u, fac, caps, sch, views, h, b, cfg):
    return run_trial(u["tool"], fac, caps, sch, views, h, b["value"], cfg["k"], cfg["rho"], u["seed"],
                  minimize_witnesses=False, budget_kind=b["kind"], nondet_reruns=cfg["nondet_reruns"])


def exec_secondary(u: dict, slot: int, cfg: dict, run_dir: str) -> dict:
    """B7 TLP as SECONDARY_ORACLE: a fixed set of seeded checks on the target's batch query path."""
    from .baselines import b7_tlp, tlp_predicate
    sch, views, h = unit_workload(cfg, run_dir, u)
    views = applicable_views(views, cfg["capability_matrix"][u["target"]])
    fac, caps = make_factory(cfg, u["target"], sch, views, slot)
    rng = random.Random(u["seed"]); divs = []
    for i in range(u["budget"]["value"]):
        hq = w3.gen_history(rng, sch, max(2, len(h))) if u["workload"] == "W3" else h[: rng.randint(1, max(1, len(h)))]
        eng = fac()
        try:
            for e in hq:
                eng.apply_transaction(e)
            eng.flush()
            xs = src(sch, hq)
            for v in views:
                if v.exposed():
                    col, const = tlp_predicate(v, sch, xs)
                    if b7_tlp(eng.query, v, sch, "duckdb", col, const)["diverges"]:
                        divs.append({"kind": "tlp", "where": "query-path", "latent": False, "history_digest": history_digest(hq),
                                     "triage": {"class": "QUERY_PATH_BUG", "candidate": False}})
        finally:
            if hasattr(eng, "destroy"):
                eng.destroy()
    return {"unit_id": u["unit_id"], "phase": u["phase"], "target": u["target"], "workload": u["workload"], "tool": u["tool"],
            "trial": 0, "unit_class": "SECONDARY_ORACLE", "checks": u["budget"]["value"], "divergences": divs,
            "first_candidate_at": None, "censored": True, "coverage": {}, "schema": sch.to_json(), "views": [v.to_json() for v in views]}


def exec_native_suite(u: dict, cfg: dict) -> dict:
    base = {"unit_id": u["unit_id"], "phase": u["phase"], "target": u["target"], "workload": "-", "tool": u["tool"], "trial": 0,
            "unit_class": "DETERMINISTIC_SUITE", "divergences": [], "first_candidate_at": None, "censored": True, "coverage": {}}
    if cfg["targets"][u["target"]]["kind"] == "simulated":
        rng = random.Random(u["seed"]); fails = 0
        for i in range(5):
            sch = w3.gen_schema(rng); vs = w3.gen_views(rng, sch); hh = w3.gen_history(rng, sch, 5)
            fails += int(judge(lambda: ToyEngine(sch, vs, "NONE"), sch, vs, hh, use_o3=False)["diverges"])
        return dict(base, suite_status="SIMULATED_SUITE_PASS" if fails == 0 else "SIMULATED_SUITE_FAIL")
    from .adapters.transport import Docker
    from .baselines import b5_run_native
    r = b5_run_native(Docker(), u["target"], cfg["timeouts"]["lifecycle_s"] * 6)
    return dict(base, suite_status=r["status"], suite_tail=r.get("tail", r.get("detail", ""))[-400:])


def _exec(u, slot, cfg=None, run_dir=None):
    return exec_unit(u, slot, cfg, run_dir)


class _Bound:
    def __init__(self, cfg, run_dir):
        self.cfg, self.run_dir = cfg, run_dir

    def __call__(self, u, slot):
        return exec_unit(u, slot, self.cfg, self.run_dir)


def committed(camp: Campaign, units: List[dict]) -> List[dict]:
    st = camp.status(); out = []
    for u in units:
        s = st.get(u["unit_id"])
        if s and s["status"] == "COMMITTED":
            out.append(json.load(open(os.path.join(camp.run_dir, "results", s["result"] + ".json"))))
    return out


# ------------------------------------------------------------------ S5 tester conformance
TRIGGERS = {  # frozen word-terminal activation tests (P3): fault -> (view name, automaton, word, lifecycle appended)
    "F1_WRONG_MULT": ("v_group", "GROUP", ("birth", "grow"), None),
    "F2_LOST_DELETE": ("v_group", "GROUP", ("grow", "shrink"), None),
    "F3_DUP_INSERT_LATENT": ("v_distinct", "DISTINCT", ("appear",), None),
    "F4_MINMAX_EXTREMUM": ("v_group", "MINMAX", ("ext-tie", "ext-remove-tied", "ext-remove-unique"), None),
    "F5_DISTINCT_DUPCOUNT_LATENT": ("v_distinct", "DISTINCT", ("appear", "add-dup"), None),
    "F6_OUTER_PAD": ("v_ljoin", "LEFTJOIN", ("pad-leave", "pad-enter"), None),
    "F7_TOPK_REFILL": ("v_topk", "TOPK", ("enter", "enter", "insert-below", "delete-refill"), None),
    "F8_LIFECYCLE_RESTORE": ("v_group", "GROUP", ("birth",), "RESTART"),
    "F9_LATENT_RESIDUAL": ("v_group", "GROUP", ("birth", "death"), None),
}


def _word_test(fault, i, seed):
    from .model import Life, src as _src
    from .realize import Unrealizable, realize
    from .suffix import SuffixUnsupported, synthesize
    vname, aut, word, lc = TRIGGERS[fault]
    for attempt in range(20):
        rng = random.Random(hmac_seed(seed, fault, i, attempt)); sch = w3.gen_schema(rng); vs = w3.gen_views(rng, sch)
        v = next(x for x in vs if x.name == vname)
        h0 = w3.gen_history(rng, sch, 4)
        try:
            frag, rec = realize(sch, v, _src(sch, h0), aut, word, setup_max=3, budget=1500)
        except Unrealizable:
            continue
        h = h0 + frag + ([Life(lc)] if lc else [])
        try:
            suf, _ = synthesize(sch, v, _src(sch, h), rec["key_value"])
        except SuffixUnsupported:
            suf = []
        return sch, vs, h, suf
    return None


def tester_conformance(cfg: dict) -> dict:
    """S5: zero false divergences on the correct engine; every in-model seeded fault detected by its frozen
    word-terminal test plus characterization suffix; the nondeterminism control never yields a candidate."""
    tc = cfg["tester_conformance"]; false_div = 0; detected = {}; f11_cands = 0; unrealized = {}
    for i in range(tc["correct_histories"]):
        rng = random.Random(hmac_seed(tc["seed"], "correct", i)); sch = w3.gen_schema(rng); vs = w3.gen_views(rng, sch)
        h = w3.gen_history(rng, sch, rng.randint(2, 10))
        if judge(lambda: ToyEngine(sch, vs, "NONE"), sch, vs, h, use_o3=False)["diverges"]:
            false_div += 1
    for f in tc["seeded_faults"]:
        detected[f] = 0; unrealized[f] = 0
        for i in range(tc["fault_histories"]):
            if f in TRIGGERS:
                case = _word_test(f, i, tc["seed"])
                if case is None:
                    unrealized[f] += 1; continue
                sch, vs, h, suf = case
            else:
                rng = random.Random(hmac_seed(tc["seed"], f, i)); sch = w3.gen_schema(rng); vs = w3.gen_views(rng, sch)
                h = w3.gen_history(rng, sch, 10); suf = []
            tr = triage(lambda: ToyEngine(sch, vs, f), sch, vs, h, suf)
            if f == "F11_NONDETERMINISM" or f in ADVERSARIAL:      # nondeterminism controls: never a candidate
                f11_cands += int(tr.get("candidate", False))
            elif tr.get("candidate"):
                detected[f] += 1
    in_model_ok = all(detected[f] == tc["fault_histories"] for f in tc["seeded_faults"] if f in IN_MODEL)
    ok = false_div == 0 and f11_cands == 0 and in_model_ok
    return {"ok": ok, "false_divergences": false_div, "detected": detected, "unrealized": unrealized,
            "nondeterminism_candidates": f11_cands, "fault_histories": tc["fault_histories"]}


# ------------------------------------------------------------------ S8 witness closure
POST_V1_7_2_TOOLS = frozenset({"ablate_deletion_matched_suffix"})


def closure_order(u: dict):
    """Witness content comes from the first unit that reaches a key. V1.7.2 order (unit_id) is kept for every V1.7.2 arm;
    arms added later sort last, so they can only create witnesses for keys no V1.7.2 arm reached (V1.8 no-regression)."""
    return (u["tool"] in POST_V1_7_2_TOOLS, u["unit_id"])


def witness_closure(cfg: dict, run_dir: str, units: List[dict]) -> List[dict]:
    wdir = os.path.join(run_dir, "witnesses"); os.makedirs(wdir, exist_ok=True); out = []; seen = set()
    for u in sorted(units, key=closure_order):
        sch = schema_from_json(u["schema"]); views = views_from_json(sch, u["views"])
        for d in u["divergences"]:
            if not d["triage"].get("candidate"):
                continue
            key = (u["target"], d["history_digest"], d["triage"]["class"])
            if key in seen:
                continue
            seen.add(key)
            wid = sha(list(key))
            wpath = os.path.join(wdir, f"{wid}.json")
            if os.path.exists(wpath):                      # resumable: each witness is committed atomically
                out.append(json.load(open(wpath))); continue
            h = history_from_canon(d["history"]); s = history_from_canon(d["suffix"])
            fac, caps = make_factory(cfg, u["target"], sch, views, 0)
            obs = {judge(fac, sch, views, h, s, use_o3=False).get("obs_digest") for _ in range(cfg["nondet_reruns"])}
            status = "NEW" if obs == {d.get("obs_digest")} else "DEMOTED_NONDETERMINISM"
            wc = cfg["witness_closure"]
            pred = lambda hh, ss: judge(fac, sch, views, hh, ss, use_o3=False)["diverges"]
            import time as _t
            wall = cfg["evidence"]["timing_mode"] == "wallclock"
            t0 = _t.monotonic()
            mh, ms, trace, cert = (h, s, [], {"slice_1_minimal": False}) if status != "NEW" else minimize(sch, views, h, s, pred, wc["min_budget"])
            t1 = _t.monotonic(); dd_counters = {"target": 0}
            dd, calls = ddmin(sch, h, lambda c: pred(c, s), wc["min_budget"], dd_counters) if status == "NEW" else (h, 0)
            t2 = _t.monotonic()
            replay_cw = bool(pred(mh, ms)) if status == "NEW" else False
            replay_dd = bool(pred(dd, s)) if status == "NEW" else False
            minimizers = [{"algorithm": "cutwitness_min", "original_length": len(h) + len(s), "final_length": len(mh) + len(ms),
                           "predicate_calls_logical": cert.get("predicate_calls_logical", 0), "predicate_calls_target": cert.get("predicate_calls_target", 0),
                           "wall_time_s": round(t1 - t0, 3) if wall else None, "replay_success": replay_cw},
                          {"algorithm": "ddmin", "original_length": len(h) + len(s), "final_length": len(dd) + len(s),
                           "predicate_calls_logical": calls, "predicate_calls_target": dd_counters["target"],
                           "wall_time_s": round(t2 - t1, 3) if wall else None, "replay_success": replay_dd}]
            w = {"id": wid, "label": label_of(cfg), "target": u["target"], "target_version": cfg["targets"][u["target"]]["version"],
                 "workload": u["workload"], "unit_id": u["unit_id"], "class": d["triage"]["class"], "status": status,
                 "signature": sha([u["target"], d["triage"]["class"], d.get("where", "")[:6]]), "schema": u["schema"], "views": u["views"],
                 "history": history_canon(mh), "suffix": history_canon(ms), "original_len": len(h), "minimized_len": len(mh),
                 "ddmin_len": len(dd), "ddmin_calls": calls, "trace": trace, "certificate": cert,
                 "terminal_digest": sha(history_canon(mh)), "replay": f"python3 -m cutwitness.replay witnesses/{wid}.json",
                 "minimizers": minimizers, "latent": bool(d.get("latent")), "tool": u["tool"], "where": d.get("where"),
                 "operators": sorted({op.kind for v in views for op in v.ops}),
                 "lifecycle_kinds": sorted({e.kind for e in h if not hasattr(e, "delta")}),
                 "original_history": history_canon(h), "original_suffix": history_canon(s)}
            atomic_write(os.path.join(wdir, f"{wid}.json"), cjson(w).encode()); out.append(w)
    return out


# ------------------------------------------------------------------ main
def digests_consistent(sealed: dict, now: dict) -> bool:
    """Resume rule: every target image must resolve to exactly the digest journaled when the run was sealed."""
    return sealed == now


def preflight_ok(cfg: dict, run_dir: str) -> dict:
    from .one_shot import preflight
    pf = preflight(cfg)
    if cfg["mode"] == "ENGINEERING_SIMULATION":
        pf["all_ok"] = True; pf["note"] = "simulation: container runtime and token not required"
    return pf


def run(cfg_path: str, run_dir: str, root: str = None) -> dict:
    root = root or pkg_root()
    try:
        cfg = load_config(cfg_path)
    except (ConfigError, OSError, ValueError) as e:
        return _final(run_dir, None, "NOT_STARTED_OPERATIONAL", f"S0 config invalid: {e}")
    try:
        return _run(cfg, run_dir, root)
    except Stop as s:
        return _final(run_dir, cfg, s.verdict, s.reason)
    except JournalCorruption as e:
        return _final(run_dir, cfg, "INCOMPLETE_NONRESUMABLE_CORRUPTION", str(e))


def _final(run_dir, cfg, verdict, reason, extra=None):
    assert verdict in VERDICTS
    os.makedirs(run_dir, exist_ok=True)
    v = {"verdict": verdict, "reason": reason, **(extra or {})}
    atomic_write(os.path.join(run_dir, "FINAL_VERDICT.json"), cjson(v).encode())
    return v


def _run(cfg, run_dir, root):
    from .one_shot import verify_package, fingerprint
    # S0 integrity
    if cfg["mode"] == "SEALED_CAMPAIGN":
        if cfg["release_state"] != "SEALED":
            raise Stop("NOT_STARTED_OPERATIONAL", "S0 release_state is not SEALED")
        vp = verify_package(root)
        if not vp["ok"]:
            raise Stop("NOT_STARTED_OPERATIONAL", f"S0 package integrity: {vp}")
    if code_digest(root) != cfg["code_tree_digest"]:
        raise Stop("NOT_STARTED_OPERATIONAL", "S0 code tree digest differs from the frozen configuration")
    os.makedirs(os.path.join(run_dir, "preseal"), exist_ok=True)
    atomic_write(os.path.join(run_dir, "preseal", "S1_fingerprint.json"), cjson(fingerprint()).encode())   # S1
    pf = preflight_ok(cfg, run_dir)                                                                          # S2
    if not pf["all_ok"]:
        raise Stop("NOT_STARTED_OPERATIONAL", f"S2 preflight: {pf}")
    from .preflight import duration_preflight, report_text
    dp = duration_preflight(cfg)
    atomic_write(os.path.join(run_dir, "preseal", "CAMPAIGN_PREFLIGHT_REPORT.txt"), report_text(dp).encode())
    if dp["CAMPAIGN_DURATION_PREFLIGHT"] != "PASS":
        raise Stop("NOT_STARTED_OPERATIONAL", f"CAMPAIGN_DURATION_PREFLIGHT=BLOCKED (projected {dp['PROJECTED_WALL_DAYS']} days, "
                                              f"{dp['EFFECTIVE_SLOTS']} effective slots, limit {dp['MAX_CAMPAIGN_DAYS']} days)")
    digests = {}
    if cfg["mode"] == "SEALED_CAMPAIGN":
        from .adapters.transport import Docker
        from .realtargets import resolve_digests
        digests = resolve_digests(Docker(), {k: v["image"] for k, v in cfg["targets"].items()}, cfg["timeouts"]["pull_s"])
    camp = Campaign(run_dir, cfg, cfg["operational_retries"]); run_id = camp.ensure_run_id()
    pre = [r for r in camp.journal.recs if r["kind"] == "STAGE_DONE" and r["payload"]["stage"] == "S2"]
    if pre and not digests_consistent(pre[0]["payload"]["image_digests"], digests):
        raise Stop("INCOMPLETE_NONRESUMABLE_CORRUPTION", "image digests changed since the run was sealed")
    if not pre:
        camp.mark_stage("S2", {"image_digests": digests, "duration_preflight": dp})
    dsd = materialize(cfg, run_dir)                                                                          # S3
    s3 = [r for r in camp.journal.recs if r["kind"] == "STAGE_DONE" and r["payload"]["stage"] == "S3"]
    if s3 and s3[0]["payload"]["datasets"] != dsd:
        raise Stop("INCOMPLETE_NONRESUMABLE_CORRUPTION", "dataset materialization is not reproducible")
    if not s3:
        camp.mark_stage("S3", {"datasets": dsd})
    real = cfg["mode"] == "SEALED_CAMPAIGN"
    if real:                                                                                                 # S4 deployment
        from .adapters.base import AdapterFailure
        from .adapters.transport import Docker, Http, PgSql
        from .isolation import ResourcePlan, orphan_cleanup
        from .realtargets import launch_slot, probe_ready
        dk = Docker(); orphan_cleanup(dk, run_id, cfg["timeouts"]["lifecycle_s"])
        plan = ResourcePlan(dp["AVAILABLE_VCPUS"], dp["AVAILABLE_RAM_BYTES"] / 2 ** 30, cfg["resources"]["per_trial_cpus"],
                            cfg["resources"]["per_trial_ram_gb"], cfg["duration_gate"]["reserve_vcpus"], cfg["duration_gate"]["reserve_ram_gib"])
        evidence = {}
        try:
            for slot in range(dp["EFFECTIVE_SLOTS"]):
                for name, info in launch_slot(cfg, run_id, slot, digests, dk, run_dir, plan.cpuset(slot)).items():
                    evidence[f"{name}-s{slot}"] = {**info, "probe": probe_ready(cfg, name, info["port"], {"sql": PgSql, "http": Http})}
        except AdapterFailure as e:
            orphan_cleanup(dk, run_id, cfg["timeouts"]["lifecycle_s"])
            camp.journal.append("STAGE_FAILED", {"stage": "S4", "deployment": str(e)})
            raise Stop("CONFORMANCE_BLOCKED", f"S4 deployment/readiness failed: {e}")
        camp.journal.append("DEPLOYMENT", {"evidence": evidence})
    if not camp.stage_done("S4"):                                                                            # S4
        rep = {}
        for tg in cfg["full"]["targets"]:
            rng = random.Random(hmac_seed(cfg["master_seed"], "S4", tg)); sch = w3.gen_schema(rng)
            views = applicable_views(w3.gen_views(rng, sch), cfg["capability_matrix"][tg])
            fac, _ = make_factory(cfg, tg, sch, views, 0)
            pin = {k: v for k, v in cfg["targets"][tg]["version"].items() if k != "pg_ivm"}
            r = run_conformance(lambda name: fac(), sch, views, pin, hmac_seed(cfg["master_seed"], "S4c", tg),
                                evidence_kind="REAL" if real else "SIMULATED")
            rep[tg] = r
            if not r["ok"]:
                cap = any(c["check"].endswith("declared_unsupported") for c in r["checks"] if not c["ok"])
                camp.journal.append("STAGE_FAILED", {"stage": "S4", "target": tg, "checks": r["checks"]})
                raise Stop("CAPABILITY_BLOCKED" if cap else "CONFORMANCE_BLOCKED", f"S4 {tg} failed live conformance")
        camp.mark_stage("S4", {"targets": sorted(rep), "evidence_kind": {t: r["evidence_kind"] for t, r in rep.items()}})
    s4 = [r for r in camp.journal.recs if r["kind"] == "STAGE_DONE" and r["payload"]["stage"] == "S4"][0]["payload"]
    if real and set(s4["evidence_kind"].values()) != {"REAL"}:
        raise Stop("CONFORMANCE_BLOCKED", "S4 evidence is not REAL target conformance for every target")
    if not camp.stage_done("S5"):                                                                            # S5
        tc = tester_conformance(cfg)
        if not tc["ok"]:
            camp.journal.append("STAGE_FAILED", {"stage": "S5", **tc})
            raise Stop("CONFORMANCE_BLOCKED", f"S5 tester conformance failed: {tc}")
        camp.mark_stage("S5", tc)
    slots = dp["EFFECTIVE_SLOTS"]; fn = _Bound(cfg, run_dir)
    pilot_units = plan_units(cfg, "pilot")                                                                   # S6
    run_units_parallel(camp, pilot_units, fn, slots)
    pres = committed(camp, pilot_units)
    pb = cfg["pilot"]["budget"]["value"]
    dec = evaluate(pres, len(pilot_units), cfg["pilot"]["signals"], pb,
                   [t for t in cfg["pilot"]["tools"] if t in BASELINE_TOOLS], cfg["pilot"]["targets"])
    if not camp.stage_done("S6"):
        if dec["decision"] == "INCOMPLETE":
            raise Stop("INCOMPLETE_OPERATIONAL_RESUMABLE", dec["reason"])
        camp.mark_stage("S6", {"decision": dec["decision"], "signals": dec["signals"]})
    crash_point("between_pilot_and_full")
    if dec["decision"] == "PILOT_NO_GO":
        final_units, verdict = pres, "COMPLETE_PILOT_NO_GO"
    else:
        full_units = plan_units(cfg, "full")                                                                 # S7
        na = [u for u in full_units if u["unit_class"] == "NOT_APPLICABLE"]
        exe = [u for u in full_units if u["unit_class"] != "NOT_APPLICABLE"]
        for u in na:
            camp.mark_not_applicable(u["unit_id"], u["applicability"])
        run_units_parallel(camp, exe, fn, slots)
        final_units = committed(camp, exe)
        if len(final_units) < len(exe):
            raise Stop("INCOMPLETE_OPERATIONAL_RESUMABLE", f"{len(exe) - len(final_units)} full-campaign units not committed")
        if not camp.stage_done("S7"):
            camp.mark_stage("S7", {"units": len(full_units)})
        verdict = "COMPLETE_FULL_CAMPAIGN"
    search_like = [u for u in final_units if u.get("unit_class", "SEARCH_TRIAL") in ("SEARCH_TRIAL", "ABLATION")]  # S8
    min_units = [u for u in plan_units(cfg, "closure")] if verdict == "COMPLETE_FULL_CAMPAIGN" else \
        [{"unit_id": f"closure|{t}|-|witness_minimization+ddmin|-", "target": t, "seed": 0, "unit_class": "MINIMIZATION"} for t in cfg["pilot"]["targets"]]
    camp.run_units(min_units, lambda mu: {"unit_id": mu["unit_id"], "unit_class": "MINIMIZATION", "target": mu["target"],
                                         "witnesses": [w["id"] for w in witness_closure(cfg, run_dir, [x for x in search_like if x["target"] == mu["target"]])]})
    wits = witness_closure(cfg, run_dir, search_like)
    from .attribution import attribution_closure                    # Amendment v1.2: evidence classification only
    attrs = attribution_closure(cfg, run_dir, wits, make_factory)
    for w in wits:
        if w["id"] in attrs:
            w["attribution"] = attrs[w["id"]]
    if not camp.stage_done("S8"):
        counts = {}
        for a in attrs.values():
            counts[a["attribution_class"]] = counts.get(a["attribution_class"], 0) + 1
        camp.mark_stage("S8", {"witnesses": sorted(w["id"] for w in wits), "latent_attribution": counts})
    crash_point("during_analysis")                                                                           # S9-S10
    lab = label_of(cfg); adir = os.path.join(run_dir, "analysis", "SCIENTIFIC" if cfg["mode"] == "SEALED_CAMPAIGN" else "SYNTHETIC_ENGINEERING")
    summ = analyze(final_units, cfg, lab, cfg["full" if verdict == "COMPLETE_FULL_CAMPAIGN" else "pilot"]["budget"]["value"], adir, wits)
    if not camp.stage_done("S10"):
        camp.mark_stage("S10", {"analysis": summ})
    crash_point("during_artifact_closure")                                                                   # S11
    files = []
    for d, _, fs in os.walk(run_dir):
        for f in fs:
            p = os.path.join(d, f); rel = os.path.relpath(p, run_dir)
            if rel.startswith(("scratch", "preseal", "journal.jsonl")) or rel in ("FINAL_VERDICT.json", "SHA256SUMS", "final_manifest.json", "run_meta.json") or ".tmp." in rel or rel.endswith(".lock"):
                continue
            files.append((rel, hashlib.sha256(open(p, "rb").read()).hexdigest()))
    files.sort()
    atomic_write(os.path.join(run_dir, "SHA256SUMS"), "".join(f"{h}  {r}\n" for r, h in files).encode())
    rdig = sha([sorted((u["unit_id"], sha(u)) for u in final_units), summ, sorted(w["id"] for w in wits)])
    if not camp.stage_done("S11"):
        camp.mark_stage("S11", {"files": len(files), "results_digest": rdig})
    _, n, head = camp.journal.verify()
    atomic_write(os.path.join(run_dir, "final_manifest.json"), cjson({"run_id": run_id, "files": files, "journal_head": head,
                                                                         "results_digest": rdig, "label": lab}).encode())
    if real:
        from .adapters.transport import Docker
        from .isolation import orphan_cleanup
        orphan_cleanup(Docker(), run_id, cfg["timeouts"]["lifecycle_s"])
    return _final(run_dir, cfg, verdict, "all frozen stages completed", {"run_id": run_id, "results_digest": rdig,      # S12
                                                                          "journal_head": head, "label": lab})
