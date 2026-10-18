import random, sys, os
from decimal import Decimal as D
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cutwitness.model import *
from cutwitness.refmodel import *
from cutwitness import transforms as T
from cutwitness.w3 import gen_schema, gen_views, gen_history
from cutwitness.oracles import reference_obs, duckdb_obs, obs_digest


def test_zset_algebra():
    a = ZSet([((1,), 2), ((2,), -1)]); b = ZSet([((1,), -2), ((3,), 1)])
    assert (a + b) == ZSet([((2,), -1), ((3,), 1)]) and (a - a) == ZSet() and (-(-a)) == a


def test_canonical_digest_stable_and_exact():
    assert cval(D("1.50")) == cval(D("1.5")) == ["d", "1.5"] and cval(1) != cval("1")
    assert ZSet([((D("2.0"), "x"), 1)]).digest() == ZSet([((D("2"), "x"), 1)]).digest()


def test_legality_pk_fk():
    s = Schema([Table("p", [("id", "int", False)], pk=[0]), Table("c", [("id", "int", False), ("p", "int", True)], pk=[0], fks=[([1], "p", [0])])])
    x = empty_state(s)
    assert not legal_state(s, apply_txn(x, Txn({"c": ZSet([((1, 9), 1)])})))[0]
    x = apply_txn(x, Txn({"p": ZSet([((9,), 1)])}))
    assert legal_state(s, apply_txn(x, Txn({"c": ZSet([((1, 9), 1)])})))[0]
    assert not legal_state(s, apply_txn(x, Txn({"p": ZSet([((9,), 1)])})))[0]


def test_history_roundtrip():
    rng = random.Random(3); s = gen_schema(rng); h = gen_history(rng, s, 15)
    h2 = history_from_canon(history_canon(h)); assert history_digest(h) == history_digest(h2)


def test_transforms_preserve_source_effect_property():
    for seed in range(60):
        rng = random.Random(seed); s = gen_schema(rng); h = gen_history(rng, s, 8)
        txi = [i for i, e in enumerate(h) if is_txn(e)]
        trials = [lambda: T.reorder(s, h, rng.randrange(len(h) - 1)), lambda: T.coalesce(s, h, rng.randrange(len(h) - 1)),
                  lambda: T.inverse_detour(s, h, rng.choice(txi), h[rng.choice(txi)].inverse()),
                  lambda: T.recurrence_detour(s, h, txi[-1], 2), lambda: T.insert_lifecycle(s, h, 2, "RESTART")]
        for f in trials:
            try:
                h1, pf = f()
            except T.IllegalTransform:
                continue
            assert pf["prefix_legal"] and pf["terminal_equal"] and prefix_legal(s, h1)[0]
            assert state_digest(src(s, h1)) == state_digest(src(s, h))


def test_split_coalesce_equivalence():
    rng = random.Random(5); s = gen_schema(rng); h = gen_history(rng, s, 10, max_rows=3)
    i = next(i for i, e in enumerate(h) if is_txn(e) and len(list(e.rows())) > 1)
    h1, _ = T.split(s, h, i, [0]); h2, _ = T.coalesce(s, h1, i)
    assert state_digest(src(s, h2)) == state_digest(src(s, h))


def test_reference_vs_duckdb_differential():
    mism = 0
    for seed in range(40):
        rng = random.Random(1000 + seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 12)
        x = src(s, h)
        if obs_digest(reference_obs(vs, x)) != obs_digest(duckdb_obs(s, vs, x)):
            mism += 1
    assert mism == 0


def test_unsupported_semantics_rejected():
    import pytest
    with pytest.raises(UnsupportedSemantics):
        GroupAgg("g", Scan("s", "t", 2), [], [("COUNT", None)])
    with pytest.raises(UnsupportedSemantics):
        GroupAgg("g", Scan("s", "t", 2), [0], [("MEDIAN", 1)])


def test_no_placeholders_in_active_path():
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cutwitness")
    for fn in os.listdir(root):
        if fn.endswith(".py"):
            txt = open(os.path.join(root, fn)).read()
            assert "TODO" not in txt and "FIXME" not in txt and "implement later" not in txt.lower(), fn
