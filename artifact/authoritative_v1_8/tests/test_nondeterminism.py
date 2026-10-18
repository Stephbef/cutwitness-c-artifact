"""Adversarial nondeterministic targets must never become class 7/8 candidate bugs."""
import random
import pytest
from cutwitness.oracles import triage
from cutwitness.toyengine import ADVERSARIAL, ToyEngine, reset_adversarial
from cutwitness.transforms import insert_lifecycle
from cutwitness.w3 import gen_history, gen_schema, gen_views


@pytest.mark.parametrize("fault", sorted(ADVERSARIAL))
@pytest.mark.parametrize("offset", range(0, 12))
def test_adversarial_target_never_counted_as_bug(fault, offset):
    rng = random.Random(500 + offset); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6)
    for with_lifecycle in (False, True):
        hh = insert_lifecycle(s, h, len(h) - 1, "RESTART")[0] if with_lifecycle else h
        reset_adversarial(offset)
        r = triage(lambda: ToyEngine(s, vs, fault), s, vs, hh)
        assert not r["candidate"], (fault, offset, r)
        assert r["class"] in ("TARGET_NONDETERMINISM", "NO_DIVERGENCE"), r


@pytest.mark.parametrize("fault", sorted(ADVERSARIAL))
def test_adversarial_target_in_trial_and_witness_closure(fault, tmp_path):
    from cutwitness.pipeline import run_trial
    rng = random.Random(9); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 6)
    reset_adversarial(0)
    r = run_trial("cutwitness_c", lambda: ToyEngine(s, vs, fault), ToyEngine.caps, s, vs, h, 4, 2, 0.1, 3, minimize_witnesses=False)
    assert all(not d["triage"].get("candidate") for d in r["divergences"])
    assert r["first_candidate_at"] is None and r["censored"]
