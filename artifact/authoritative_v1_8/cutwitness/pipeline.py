"""One scientific trial: candidate generation, reduction, frozen scoring, execution, oracles, triage, witnesses."""
from __future__ import annotations
import random
from typing import Callable, Dict, List
from .equivalence import ClassIndex
from .model import Life, Txn, apply_txn, empty_state, history_canon, history_digest, is_txn, sha, src
from .oracles import judge, minimize, path_vs_path, triage
from .realize import Unrealizable, realize
from .refmodel import touched, labels_for
from .sta import AUTOMATA, Coverage, feasible_words, label_words
from .suffix import SuffixUnsupported, deletion_matched_suffix, opportunity_length, random_suffix, synthesize
from . import transforms as T

TOOLS = {
    "cutwitness_c": dict(suffix=True, guidance=True, reduction=True, lifecycle="semantic", words=True, pairs=True),
    "ablate_no_suffix": dict(suffix=False, guidance=True, reduction=True, lifecycle="semantic", words=True, pairs=True),
    # Amendment v1.4: matched control; identical to cutwitness_c except the suffix-construction rule
    "ablate_random_suffix": dict(suffix="random", guidance=True, reduction=True, lifecycle="semantic", words=True, pairs=True),
    "ablate_deletion_matched_suffix": dict(suffix="random_delmatched", guidance=True, reduction=True, lifecycle="semantic", words=True, pairs=True),
    "ablate_no_guidance": dict(suffix=True, guidance=False, reduction=True, lifecycle="semantic", words=True, pairs=True),
    "ablate_no_reduction": dict(suffix=True, guidance=True, reduction=False, lifecycle="semantic", words=True, pairs=True),
    "ablate_random_lifecycle": dict(suffix=True, guidance=True, reduction=True, lifecycle="random", words=True, pairs=True),
    "baseline_random_clean": dict(suffix=False, guidance=False, reduction=False, lifecycle="none", words=False, pairs=False),
    "baseline_random_te": dict(suffix=False, guidance=False, reduction=False, lifecycle="random", words=False, pairs=True),
    "baseline_stateful_fuzz": dict(suffix=False, guidance=False, reduction=False, lifecycle="none", words=False, pairs=False, gen="b3"),
    "baseline_zippy": dict(suffix=False, guidance=False, reduction=False, lifecycle="none", words=False, pairs=False, gen="b4"),
    "baseline_source_por": dict(suffix=False, guidance=False, reduction="source", lifecycle="random", words=False, pairs=True),
    "baseline_tlp": dict(suffix=False, guidance=False, reduction=False, lifecycle="none", words=False, pairs=False, gen="tlp"),
}
SEMANTIC_POINTS = {"death", "bulk-death", "ext-remove-unique", "ext-remove-tied", "pad-enter", "disappear", "delete-refill"}


def _mutate(schema, h, rng):
    """One random sound terminal-equivalence transformation (with proof) or None."""
    for _ in range(6):
        op = rng.choice(["reorder", "split", "coalesce", "inverse", "recurrence"])
        txi = [i for i, e in enumerate(h) if is_txn(e)]
        try:
            if op == "reorder" and len(h) > 1:
                i = rng.randrange(len(h) - 1); return T.reorder(schema, h, i)
            if op == "split" and txi:
                i = rng.choice(txi); n = len(list(h[i].rows()))
                if n > 1:
                    return T.split(schema, h, i, [rng.randrange(n)])
            if op == "coalesce" and len(h) > 1:
                i = rng.randrange(len(h) - 1); return T.coalesce(schema, h, i)
            if op == "inverse" and txi:
                i = rng.choice(txi); return T.inverse_detour(schema, h, i, h[i].inverse())
            if op == "recurrence" and len(txi) >= 2:
                return T.recurrence_detour(schema, h, txi[-1], rng.randint(1, 2))
        except T.IllegalTransform:
            continue
    return None


def _lifecycle_variant(schema, views, h, kinds, mode, rng):
    if not kinds or mode == "none":
        return None
    kind = rng.choice(sorted(kinds))
    pos = None
    placement = "random"
    if mode == "semantic":
        x = empty_state(schema)
        cands = []
        for i, e in enumerate(h):
            if is_txn(e):
                x1 = apply_txn(x, e)
                for v in views:
                    ops = {o.nid: o for o in v.ops}
                    for (nid, k), ent in touched(v, x, x1).items():
                        if any(lab in SEMANTIC_POINTS for _, lab, _ in labels_for(ops[nid], *ent)):
                            cands.append(i)
                x = x1
        pos = rng.choice(cands) if cands else None
        placement = "semantic" if cands else "semantic_fallback_random"
    if pos is None:
        pos = rng.randrange(len(h)) if h else -1
    try:
        h1, proof = T.insert_lifecycle(schema, h, pos, kind)
        proof["placement"] = placement          # Patch-2: observation only
        return h1, proof
    except T.IllegalTransform:
        return None


def run_trial(tool: str, factory: Callable, caps: dict, schema, views, seed_history: List, budget: int,
              k: int, rho: float, seed: int, minimize_witnesses: bool = True, budget_kind: str = "executions",
              nondet_reruns: int = 10) -> dict:
    import time as _time
    from .baselines import ZippyModel, b3_stateful_fuzz_history, b7_tlp, source_fingerprint, tlp_predicate
    from .oracles import ExecutionRecorder, category
    cfg = TOOLS[tool]; rng = random.Random(seed)
    t_start = _time.monotonic()
    first_cand = None
    seen_source = set()

    def spent():
        return execs if budget_kind == "executions" else _time.monotonic() - t_start
    xrec = ExecutionRecorder(lambda: execs if budget_kind == "executions" else round(_time.monotonic() - t_start, 3))
    first_latent = None; first_latent_witness = None
    from . import oracles as _orc
    _prev_rec = _orc._REC; _orc._REC = xrec
    cov = Coverage(k); idx = ClassIndex(schema, views, rho, seed)
    _rho_cls, _rho_cid, _rho_obs, _rho_n = {}, {}, [], {"pruned": 0, "selected": 0}   # instrumentation state (no rng use)
    exposed = [v for v in views if v.exposed()]
    words_todo = []
    if cfg["words"]:
        for v in exposed:
            for aut in sorted({a for a, _, _ in labels_for(v.top, *_dummy(v))}):
                for w in sorted(feasible_words(aut, k)):
                    words_todo.append((v, aut, w))
        rng.shuffle(words_todo)
    lc_kinds = set(caps["lifecycle"]) - {"CHECKPOINT"}
    execs = 0; first_div = None; divergences = []; realized = 0; unrealizable = 0; lc_pairs = set()
    base = src(schema, seed_history)
    pool: List[tuple] = []
    while spent() < budget:
        if cfg.get("gen") == "tlp":
            hq = gen_history_local(rng, schema, max(2, len(seed_history)))
            eng = factory()
            try:
                for e in hq:
                    eng.apply_transaction(e)
                eng.flush()
                for v in exposed:
                    child = v.top.child if not hasattr(v.top, "left") else v.top
                    tb = schema.tables[linear_table(v)]
                    col, const = tlp_predicate(v, schema, src(schema, hq))
                    r = b7_tlp(eng.query, v, schema, "duckdb", col, const)
                    if r["diverges"]:
                        divergences.append({"kind": "tlp", "where": "query-path", "triage": {"class": "QUERY_PATH_BUG", "candidate": False},
                                            "history_digest": history_digest(hq), "latent": False})
            finally:
                if hasattr(eng, "destroy"):
                    eng.destroy()
            xrec.rows.append({"seq": len(xrec.rows), "category": "tlp_check", "executed": True, "history_id": history_digest(hq),
                              "history_length": len(hq), "t": xrec.clock(), "outcome": "EXECUTED"})
            cov.update(label_words(schema, views, hq)); execs += 1
            continue
        # -- candidate generation
        cands = []
        if cfg["words"] and words_todo:
            v, aut, w = words_todo.pop()
            try:
                frag, rec = realize(schema, v, base, aut, w)
                realized += 1; cands.append(("word", seed_history + frag, v, rec))
            except Unrealizable:
                unrealizable += 1
        if not cands or rng.random() < 0.5:
            fresh = list(seed_history)
            if cfg["pairs"]:
                m = _mutate(schema, fresh, rng)
                if m:
                    cands.append(("pair", m[0], None, m[1]))
            elif cfg.get("gen") == "b3":
                cands.append(("b3", b3_stateful_fuzz_history(rng, schema, len(seed_history), lc_kinds), None, None))
            elif cfg.get("gen") == "b4":
                cands.append(("b4", ZippyModel(schema).history(rng, len(seed_history) + 4, lc_kinds), None, None))
            else:
                cands.append(("random", gen_history_local(rng, schema, len(seed_history)), None, None))
        if cands and cfg["lifecycle"] != "none":
            lv = _lifecycle_variant(schema, views, cands[0][1], lc_kinds, cfg["lifecycle"], rng)
            if lv:
                cands.append(("lifecycle", lv[0], cands[0][2], lv[1]))
        # -- reduction (sound only within E_loc) + rho sampling of non-canonical members
        sel = []
        for c in cands:
            if cfg["reduction"] == "source":
                fp = source_fingerprint(schema, c[1])
                if fp in seen_source and rng.random() >= rho:
                    continue
                seen_source.add(fp)
            elif cfg["reduction"]:
                _cid, new = idx.add(c[1])
                if not new and rng.random() >= rho:                  # identical rng consumption to the frozen code
                    _rho_n["pruned"] += 1
                    continue
                _hd = history_digest(c[1]); _rho_cid[_hd] = _cid        # stable key (never id(): ids of freed tuples are reused)
                if new:
                    _rho_cls.setdefault(_cid, {"rep": _hd, "obs": None})
                else:
                    _rho_n["selected"] += 1
                    _rho_obs.append({"equivalence_class_id": _cid, "representative_history_id": _rho_cls.get(_cid, {}).get("rep"),
                                     "member_history_id": history_digest(c[1]), "is_representative": False, "selected_as_rho_sample": True,
                                     "rho_sampling_seed": seed, "operator_key_fingerprint": _cid.split(":")[0], "executed": False,
                                     "representative_output_digest": None, "sampled_member_output_digest": None, "equal": None,
                                     "comparison_status": "NOT_COMPARABLE", "_id": _hd})
            sel.append(c)
        _sel_ids = {id(c) for c in sel}                        # Patch-2: record generated-but-unexecuted candidates
        for c in cands:
            if id(c) not in _sel_ids:
                xrec.rows.append({"seq": len(xrec.rows), "category": "search", "executed": False, "history_id": history_digest(c[1]),
                                  "history_length": len(c[1]), "t": xrec.clock(), "outcome": "PRUNED_EQUIVALENT", "candidate_kind": c[0]})
        if not sel:
            execs += 1; continue
        # -- frozen scoring: new realizable k-words, then new (label, lifecycle) pairs, then real-seed tie-break
        def score(c):
            ww = label_words(schema, views, c[1])
            lcp = sum(1 for e in c[1] if not is_txn(e))
            return (cov.novelty(ww) if cfg["guidance"] else 0, lcp, 0, history_digest(c[1]))
        sel.sort(key=score, reverse=True)
        for c in sel[1:]:
            xrec.rows.append({"seq": len(xrec.rows), "category": "search", "executed": False, "history_id": history_digest(c[1]),
                              "history_length": len(c[1]), "t": xrec.clock(), "outcome": "NOT_SELECTED", "candidate_kind": c[0]})
        _hd0 = history_digest(sel[0][1])
        kind, h, v, proof = sel[0]
        cov.update(label_words(schema, views, h))
        suffix = []
        if cfg["suffix"]:
            tv = v or (exposed[0] if exposed else None)
            if tv is not None:
                x = src(schema, h)
                keys = sorted(tv.top.key_rows(x, {}).keys(), key=repr)
                for key in keys[:1]:
                    try:
                        if cfg["suffix"] == "random":       # matched control: same opportunity, same key, same length
                            suffix = random_suffix(schema, tv, x, key, opportunity_length(schema, tv, x, key),
                                                   random.Random(_suffix_seed(seed, execs)))
                        elif cfg["suffix"] == "random_delmatched":   # V1.8: same opportunity, key, length and number of deletes
                            directed, _ = synthesize(schema, tv, x, key)
                            suffix = deletion_matched_suffix(schema, tv, x, key, directed, random.Random(_delmatched_seed(seed, execs)))
                        else:
                            suffix, _ = synthesize(schema, tv, x, key)
                    except SuffixUnsupported:
                        suffix = []
        _row_i = len(xrec.rows)
        verdict = judge(factory, schema, views, h, suffix, use_o3=False)
        if _row_i < len(xrec.rows):
            _lc_meta = []
            _ins = (proof or {}).get("params", {}).get("i", -2) + 1 if kind == "lifecycle" else None
            for _pos, _e in enumerate(h):
                if not is_txn(_e):
                    _pl = (proof.get("placement") if _pos == _ins else "generator") if kind in ("lifecycle", "b3", "b4") else "inherited"
                    _lc_meta.append({"type": _e.kind, "position": _pos, "placement": _pl, "support": "SUPPORTED"})
            xrec.rows[_row_i].update({"candidate_kind": kind, "lifecycle_events": _lc_meta})
        if RHO_INSTRUMENTATION and _hd0 in _rho_cid:              # bind observations (cut + every suffix step)
            _cid = _rho_cid[_hd0]; _ob = (verdict.get("obs_digest"), tuple(verdict.get("step_digests", [])))
            _cls = _rho_cls.get(_cid)
            if _cls is not None and _cls["rep"] == _hd0 and _cls["obs"] is None:
                _cls["obs"] = None if verdict.get("error") else _ob
            for _r in _rho_obs:
                if _r.get("_id") == _hd0 and not _r["executed"]:
                    _r["executed"] = True; _r["sampled_member_output_digest"] = sha(list(_ob))
                    if verdict.get("error"):
                        _r["comparison_status"] = "SAMPLE_ERROR"
                    elif _cls is None or _cls["obs"] is None:
                        _r["comparison_status"] = "REPRESENTATIVE_UNAVAILABLE"
                    else:
                        _r["representative_output_digest"] = sha(list(_cls["obs"])); _r["equal"] = _cls["obs"] == _ob
                        _r["comparison_status"] = "MATCH" if _r["equal"] else "DIVERGENCE"
        execs += 1
        if kind == "pair" and cfg["pairs"] and execs < budget:
            execs += 1
            with category("path_pair"):
                _pv = path_vs_path(factory, seed_history, h)
            if _pv:
                verdict = dict(verdict); verdict["diverges"] = True; verdict.setdefault("where", "path-vs-path")
        if verdict["diverges"]:
            if first_div is None:
                first_div = spent()
            with category("triage"):
                tri = triage(factory, schema, views, h, suffix, caps)
            if tri.get("candidate") and first_cand is None:
                first_cand = spent()
            if RHO_INSTRUMENTATION and "NONDETERMIN" in str(tri.get("class", "")):
                for _r in _rho_obs:
                    if _r.get("_id") == _hd0 and _r["comparison_status"] == "DIVERGENCE":
                        _r["comparison_status"] = "NONDETERMINISTIC"
            if tri.get("candidate") and str(verdict.get("where", "")).startswith("suffix") and first_latent is None:
                first_latent = spent(); first_latent_witness = history_digest(h)     # FC holds at the cut, CC fails
            wit = {"kind": kind, "where": verdict.get("where"), "triage": tri, "history_digest": history_digest(h),
                   "latent": str(verdict.get("where", "")).startswith("suffix"), "obs_digest": verdict.get("obs_digest"),
                   "history": history_canon(h), "suffix": history_canon(suffix)}
            if minimize_witnesses and tri.get("candidate") and len(divergences) < 3:
                pred = lambda hh, ss: judge(factory, schema, views, hh, ss, use_o3=False)["diverges"]
                with category("minimization"):
                    mh, ms, trace, cert = minimize(schema, views, h, suffix, pred, budget=150)
                wit.update({"minimized_len": len(mh), "minimized_suffix_len": len(ms), "certificate": cert,
                            "minimization_trace_len": len(trace), "witness_history": history_canon(mh),
                            "witness_suffix": history_canon(ms)})
            divergences.append(wit)
    _orc._REC = _prev_rec
    _executed = [r for r in xrec.rows if r["executed"] and r["category"] in ("search", "path_pair", "tlp_check")]
    return {"first_latent_candidate_at": first_latent, "first_latent_witness": first_latent_witness, "latent_censored": first_latent is None,
            "histories_executed": len(_executed), "lifecycle_events_executed": sum(len(r.get("lifecycle_events", [])) for r in _executed),
            "rho_sampling": ({"classes_formed": len(_rho_cls), "members_pruned": _rho_n["pruned"], "sampled_selected": _rho_n["selected"],
                              "sampled_executed": sum(1 for r in _rho_obs if r["executed"]),
                              "observations": [{k: v for k, v in r.items() if k != "_id"} for r in _rho_obs]}
                             if RHO_INSTRUMENTATION and cfg["reduction"] is True else None),
            "execution_log": xrec.rows, **_old_keys(tool, execs, budget_kind, first_div, first_cand, divergences, cov, idx, realized, unrealizable)}


def _old_keys(tool, execs, budget_kind, first_div, first_cand, divergences, cov, idx, realized, unrealizable):
    return {"tool": tool, "executions": execs if budget_kind == "executions" else None, "first_divergence_exec": first_div,
            "first_candidate_at": first_cand, "budget_kind": budget_kind,
            "censored": first_cand is None, "divergences": divergences, "coverage": cov.summary(),
            "classes": sum(len(b) for b in idx.classes.values()), "realized_words": realized,
            "unrealizable_words": unrealizable}


RHO_INSTRUMENTATION = True        # Equivalence-sampling instrumentation amendment v1: logging only, never selection
RHO_STATUSES = ("MATCH", "DIVERGENCE", "REPRESENTATIVE_UNAVAILABLE", "SAMPLE_ERROR", "NONDETERMINISTIC", "NOT_COMPARABLE")


def _delmatched_seed(seed: int, exec_index: int) -> int:
    """Domain-separated stream for the V1.8 deletion-matched control; independent of the search and random-suffix streams."""
    import hashlib
    return int.from_bytes(hashlib.sha256(f"deletion-matched|{seed}|{exec_index}".encode()).digest()[:8], "big")


def _suffix_seed(seed: int, exec_index: int) -> int:
    """HMAC-style derivation for the random-suffix stream; independent of the search RNG (which stays identical)."""
    import hashlib
    return int.from_bytes(hashlib.sha256(f"random-suffix|{seed}|{exec_index}".encode()).digest()[:8], "big")


def _dummy(view):
    from .refmodel import empty_key_state, key_delta
    e = empty_key_state(view.top)
    return e, e, key_delta(view.top, e, e)


def gen_history_local(rng, schema, n):
    from .w3 import gen_history
    return gen_history(rng, schema, n)


def linear_table(view):
    from .refmodel import linear_source
    ch = view.top.child if hasattr(view.top, "child") else view.top.left
    return linear_source(ch)[0]
