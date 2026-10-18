import random, sys, os, copy
from decimal import Decimal as D
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cutwitness.model import *
from cutwitness.refmodel import *
from cutwitness.equivalence import fingerprint, independent
from cutwitness.sta import AUTOMATA, feasible_words, label_words
from cutwitness.suffix import synthesize
from cutwitness.realize import realize, Unrealizable
from cutwitness.toyengine import ToyEngine, FAULTS, IN_MODEL
from cutwitness.oracles import judge, minimize, triage, reference_obs, obs_digest
from cutwitness.w3 import gen_schema, gen_views, gen_history
from cutwitness import transforms as T


def _setup(seed, n=10):
    rng = random.Random(seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, n)
    return rng, s, vs, h


def test_p2_independent_swaps_preserve_fingerprint_and_local_engine_state():
    checked = 0
    for seed in range(40):
        rng, s, vs, h = _setup(seed)
        x = empty_state(s)
        for i in range(len(h) - 1):
            if independent(s, vs, x, h[i], h[i + 1]):
                try:
                    h2, _ = T.reorder(s, h, i)      # frozen precondition: both orders must be legal
                except T.IllegalTransform:
                    x = apply_txn(x, h[i]); continue
                assert fingerprint(s, vs, h)[0] == fingerprint(s, vs, h2)[0]
                for f in ("NONE", "F1_WRONG_MULT", "F2_LOST_DELETE", "F4_MINMAX_EXTREMUM", "F3_DUP_INSERT_LATENT"):
                    a, b = ToyEngine(s, vs, f), ToyEngine(s, vs, f)
                    for e in h: a.apply_transaction(e)
                    for e in h2: b.apply_transaction(e)
                    assert obs_digest(a.read_views()) == obs_digest(b.read_views())
                    assert repr(sorted((k, repr(v)) for k, v in a.ks["v_group"].items())) == repr(sorted((k, repr(v)) for k, v in b.ks["v_group"].items()))
                checked += 1
            x = apply_txn(x, h[i])
    assert checked > 10


def test_observed_labels_are_paths_of_frozen_automata():
    bad = 0; total = 0
    for seed in range(30):
        rng, s, vs, h = _setup(seed, 14)
        words = label_words(s, vs, h)
        for (nid, key, aut), labs in ((k, v) for k, v in words.items() if k != "__tags__"):
            if aut not in ("GROUP", "DISTINCT", "MINMAX"):
                continue
            init, tr = AUTOMATA[aut]; states = {init}
            for lab in labs:
                total += 1
                nxt = set()
                for st in states:
                    nxt |= set(tr.get((st, lab), []))
                if not nxt:
                    bad += 1; break
                states = nxt
    assert total > 50 and bad == 0


def test_correct_engine_zero_false_divergences_with_lifecycle():
    kinds = ["RESTART", "KILL_RECOVER", "CHECKPOINT", "RESTORE_LATEST", "COMPACT", "RESCALE", "REPLACE_VIEW_IDENTICAL"]
    for seed in range(120):
        rng, s, vs, h = _setup(5000 + seed, 8)
        for _ in range(2):
            h, _ = T.insert_lifecycle(s, h, rng.randrange(len(h)), rng.choice(kinds))
        v = judge(lambda: ToyEngine(s, vs, "NONE"), s, vs, h, use_o3=False)
        assert not v["diverges"], (seed, v)


def _latent_case(fault):
    s = Schema([Table("t0", [("id", "int", False), ("k", "int", False), ("v", "dec", True), ("s", "text", False)], pk=[0])])
    ar = {"t0": 4}
    if fault == "F9_LATENT_RESIDUAL":
        vs = [View("v_group", GroupAgg("vg/g", Scan("vg/s", "t0", 4), [1], [("COUNT", None), ("SUM", 2)]))]
        h = [Txn({"t0": ZSet([((1, 7, D("5"), "a"), 1)])}), Txn({"t0": ZSet([((1, 7, D("5"), "a"), -1)])})]
        key = (7,)
    else:
        vs = [View("v_distinct", Distinct("vd/d", Project("vd/p", Scan("vd/s", "t0", 4), [1, 3])))]
        h = [Txn({"t0": ZSet([((1, 7, D("5"), "a"), 1)])}), Txn({"t0": ZSet([((2, 7, D("6"), "a"), 1)])})]
        key = (7, "a")
    return s, vs, h, key


def test_latent_faults_need_continuation_suffix():
    for fault in ("F9_LATENT_RESIDUAL", "F3_DUP_INSERT_LATENT", "F5_DISTINCT_DUPCOUNT_LATENT"):
        s, vs, h, key = _latent_case(fault)
        fac = lambda: ToyEngine(s, vs, fault)
        assert not judge(fac, s, vs, h)["diverges"], fault          # invisible at the current cut
        suf, rec = synthesize(s, vs[0], src(s, h), key)
        v = judge(fac, s, vs, h, suf)
        assert v["diverges"] and v["where"].startswith("suffix"), (fault, v)
        assert not judge(lambda: ToyEngine(s, vs, "NONE"), s, vs, h, suf)["diverges"]


def test_lemma_d_group_drain_probe_finite_enumeration():
    """Every corrupted COUNT/SUM/MIN group state distinguishable by some continuation is distinguished by W_T(a)."""
    s = Schema([Table("t0", [("id", "int", False), ("k", "int", False), ("v", "dec", True), ("s", "text", False)], pk=[0])])
    v = View("v_group", GroupAgg("vg/g", Scan("vg/s", "t0", 4), [1], [("COUNT", None), ("SUM", 2), ("MIN", 2)]))
    vals = [D("1"), D("2")]
    import itertools
    count = 0
    for n in (1, 2):
        for combo in itertools.product(vals, repeat=n):
            rows = [(i + 1, 3, combo[i], "a") for i in range(n)]
            h = [Txn({"t0": ZSet([(r, 1) for r in rows])})]
            x = src(s, h); suf, _ = synthesize(s, v, x, (3,))
            for extra in [((99, 3, D("1"), "a"), 1), ((98, 3, D("2"), "a"), 1), (rows[0], -1), (rows[0], 1)]:
                eng = ToyEngine(s, [v], "NONE")
                for e in h: eng.apply_transaction(e)
                eng.ks["v_group"][(3,)] = eng.ks["v_group"][(3,)] + ZSet([extra])   # inject state corruption a' != a
                cur = x; outs = []
                for t in suf:
                    eng.apply_transaction(t); cur = apply_txn(cur, t)
                    outs.append(obs_digest(eng.read_views()) == obs_digest(reference_obs([v], cur)))
                assert not all(outs), (combo, extra)
                count += 1
    assert count >= 20


def test_realizer_post_check_exact_and_rate():
    rng, s, vs, h = _setup(77, 6)
    base = src(s, h); ok = 0; tried = 0
    for v in vs:
        if not v.exposed():
            continue
        for aut in ("GROUP", "DISTINCT", "TOPK", "JOIN", "MINMAX", "LEFTJOIN"):
            for w in sorted(feasible_words(aut, 1)):
                try:
                    frag, rec = realize(s, v, base, aut, w)
                except Unrealizable:
                    tried += 1; continue
                except Exception:
                    tried += 1; continue
                tried += 1; ok += 1
                assert rec["post_check"] == "exact" and prefix_legal(s, h + frag)[0]
    assert ok >= 12, (ok, tried)


def test_p3_seeded_fault_triggered_by_realized_word():
    rng, s, vs, h = _setup(8, 4)
    v = next(v for v in vs if v.name == "v_group")
    frag, rec = realize(s, v, src(s, h), "GROUP", ("grow", "shrink"))
    hh = h + frag
    key_rows = [k for k in v.top.key_rows(src(s, hh), {})]
    assert judge(lambda: ToyEngine(s, vs, "F2_LOST_DELETE"), s, vs, hh)["diverges"]


def test_triage_classes():
    s, vs, h, key = _latent_case("F9_LATENT_RESIDUAL")
    suf, _ = synthesize(s, vs[0], src(s, h), key)
    assert triage(lambda: ToyEngine(s, vs, "F9_LATENT_RESIDUAL"), s, vs, h, suf)["class"] == "TARGET_MAINTENANCE_BUG"
    assert triage(lambda: ToyEngine(s, vs, "F11_NONDETERMINISM"), s, vs, h)["class"] in ("TARGET_NONDETERMINISM", "NO_DIVERGENCE")
    rng, s2, vs2, h2 = _setup(21, 8)
    g = next(v for v in vs2 if v.name == "v_group")
    hl, _ = T.insert_lifecycle(s2, h2, len(h2) - 1, "RESTART")
    fac = lambda: ToyEngine(s2, vs2, "F8_LIFECYCLE_RESTORE")
    r = triage(fac, s2, vs2, hl)
    assert r["class"] in ("LIFECYCLE_RECOVERY_BUG", "NO_DIVERGENCE")


def test_minimizer_preserves_divergence_and_certifies():
    rng, s, vs, h = _setup(31, 10)
    fac = lambda: ToyEngine(s, vs, "F2_LOST_DELETE")
    if not judge(fac, s, vs, h)["diverges"]:
        return
    pred = lambda hh, ss: judge(fac, s, vs, hh, ss, use_o3=False)["diverges"]
    mh, ms, trace, cert = minimize(s, vs, h, [], pred)
    assert pred(mh, ms) and len(mh) <= len(h) and cert["slice_1_minimal"]


def test_prefix_trie_executor_verdict_equivalent_to_plain():
    from cutwitness.executor import trie_execute, plain_execute
    for seed in range(15):
        rng, s, vs, h = _setup(900 + seed, 8)
        hs = [h]
        for _ in range(6):
            try:
                hs.append(T.insert_lifecycle(s, h[: rng.randrange(1, len(h))], 0, "RESTART")[0] + h[rng.randrange(len(h)):])
            except T.IllegalTransform:
                pass
            hs.append(h[: rng.randrange(1, len(h) + 1)])
        for f in ("NONE", "F2_LOST_DELETE", "F8_LIFECYCLE_RESTORE"):
            a = trie_execute(lambda: ToyEngine(s, vs, f), hs); b = plain_execute(lambda: ToyEngine(s, vs, f), hs)
            assert {k: v for k, v in a.items() if k != "__steps__"} == {k: v for k, v in b.items() if k != "__steps__"}
            assert a["__steps__"] <= b["__steps__"]


def test_nondeterminism_control_never_counted_as_bug_multiview():
    """Regression: with many views per read the control must still be classified as nondeterminism."""
    for seed in range(6):
        rng, s, vs, h = _setup(70000 + seed, 6)
        r = triage(lambda: ToyEngine(s, vs, "F11_NONDETERMINISM"), s, vs, h)
        assert r["class"] in ("TARGET_NONDETERMINISM", "NO_DIVERGENCE") and not r["candidate"], r
