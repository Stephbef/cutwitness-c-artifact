"""Amendment v1.6: E3 canonical incremental replay. Post-witness only; never touches search."""
import random
import pytest
from cutwitness import attribution as AT
from cutwitness.model import apply_txn, empty_state, is_txn, legal_state, src
from cutwitness.toyengine import ToyEngine
from cutwitness.w3 import gen_history, gen_schema, gen_views


def _case(seed):
    rng = random.Random(seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 8)
    return s, vs, h


@pytest.mark.parametrize("seed", range(12))
def test_canonical_history_reaches_exactly_src_legally_and_independently(seed):
    s, vs, h = _case(seed)
    ch, independent, legal = AT.canonical_history(s, h)
    assert legal and all(is_txn(t) for t in ch)
    cur = empty_state(s)
    for t in ch:
        assert all(m > 0 for z in t.delta.values() for _, m in z.items_sorted())          # inserts only
        assert sum(m for z in t.delta.values() for _, m in z.items_sorted()) == 1          # one row per transaction
        cur = apply_txn(cur, t); assert legal_state(s, cur)[0]                             # every prefix legal
    assert cur == src(s, h)                                                                # exactly src(h)
    assert [t.canon() for t in AT.canonical_history(s, h)[0]] == [t.canon() for t in ch]    # deterministic
    if any(m < 0 for e in h if is_txn(e) for z in e.delta.values() for _, m in z.items_sorted()):
        assert independent                                                                 # differs from a history with deletions


@pytest.mark.parametrize("e2,e3,cls,detail", [(True, True, "HISTORY_CONDITIONED_LATENT", "STRONG_HISTORY_CONDITIONED"),
                                               (False, False, "CONTINUATION_TRIGGERED", "CONTINUATION_TRIGGERED"),
                                               (True, False, "UNRESOLVED_ATTRIBUTION", "PATH_CONSTRUCTION_SENSITIVE"),
                                               (False, True, "UNRESOLVED_ATTRIBUTION", "PATH_CONSTRUCTION_SENSITIVE")])
def test_e3_decision_table(monkeypatch, e2, e3, cls, detail):
    s, vs, h = _case(3)
    fl = [t.canon() for t in AT.fresh_load(s, h)]
    def fake(fac, schema, views, hist, suffix):
        if hist is h:
            where = "suffix@1"
        elif [t.canon() for t in hist] == fl:
            where = "PASS" if e2 else "suffix@1"
        else:
            where = "PASS" if e3 else "suffix@1"
        return {"error": None, "fc_at_cut": True, "where": where, "obs": "o", "steps": []}
    monkeypatch.setattr(AT, "_replay", fake)
    r = AT.attribute(None, s, vs, h, [], 3)
    assert (r["attribution_class"], r["attribution_detail"]) == (cls, detail)
    assert r["canonical_path_result"] != "NOT_RUN" and r["attribution_protocol"].startswith("E1/E2/E3")


def test_e3_on_real_toy_faults_history_and_continuation():
    """History-conditioned residual stays history-conditioned under E3; the delete-path defect stays continuation-triggered."""
    from tests.test_attribution import S, V, _latent_case                    # reuse the v1.2 fixtures
    for fault, cls in (("F9_LATENT_RESIDUAL", "HISTORY_CONDITIONED_LATENT"), ("F2_LOST_DELETE", "CONTINUATION_TRIGGERED")):
        h, c = _latent_case(fault)
        r = AT.attribute(lambda: ToyEngine(S, [V], fault), S, [V], h, c, 3)
        assert r["attribution_class"] == cls, (fault, r)
        assert r["canonical_path_result"].startswith("FC_PASS") and r["canonical_independent_of_history"]


def test_e3_does_not_touch_search():
    import inspect
    from cutwitness import pipeline
    assert "canonical_history" not in inspect.getsource(pipeline) and "attribution" not in inspect.getsource(pipeline.run_trial)
