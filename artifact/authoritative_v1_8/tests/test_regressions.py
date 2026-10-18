"""Named regressions for the five defects fixed before Amendment v1.1 (each also emulates the pre-fix behaviour)."""
import json, os, random
from decimal import Decimal as D
from cutwitness.adapters.base import CapabilityUnsupported
from cutwitness.adapters.pgwire import PgIvmAdapter, RisingWaveAdapter
from cutwitness.adapters.feldera import FelderaAdapter, _parse
from cutwitness.model import Schema, Table, Txn, ZSet, src
from cutwitness.refmodel import Filter, GroupAgg, Scan, View
from cutwitness.targetsql import postprocess, target_sql, CanonicalizationError
import pytest


def test_regression_1_risingwave_upgrade_unsupported_and_no_state_leak(mocks):
    m = mocks(1); mk, rw, drw = m["rw"]; a = mk("r1")
    before = list(drw.log)
    with pytest.raises(CapabilityUnsupported):
        a.lifecycle("UPGRADE")
    assert drw.log == before, "refused UPGRADE must not touch the container"
    for cls in (PgIvmAdapter, RisingWaveAdapter, FelderaAdapter):
        assert cls.LIFECYCLE["UPGRADE"] == "UNSUPPORTED"
    assert not hasattr(RisingWaveAdapter, "_replace_container")  # pre-fix path that swapped container versions is gone
    cfg = json.load(open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "campaign", "FROZEN_CAMPAIGN.yaml")))
    assert all(cfg["capability_matrix"][t]["lifecycle"]["UPGRADE"] == "UNSUPPORTED" for t in cfg["capability_matrix"])


def _avg_view():
    s = Schema([Table("t0", [("id", "int", False), ("k", "int", False), ("v", "dec", True)], pk=[0])])
    return s, View("v", GroupAgg("g", Scan("s", "t0", 3), [1], [("COUNT", None), ("AVG", 2)]))


def test_regression_2_avg_canonicalization_and_exact_types():
    s, v = _avg_view(); q, names = target_sql(v, s, "duckdb")
    exact = (D("7") / 3).quantize(D("0.000001"))
    z = postprocess(v, s, names, [(1, D("3"), 2.3333333333333335, D("7.0000"), 3)])      # binary AVG within 1e-9
    assert z == ZSet([((1, 3, exact), 1)])
    z = postprocess(v, s, names, [(1, 3, D("2.3333"), D("7"), 3)])                        # decimal AVG at scale 4
    assert z == ZSet([((1, 3, exact), 1)])
    bad = postprocess(v, s, names, [(1, 3, 2.5, D("7"), 3)])
    row = next(iter(bad.d)); assert isinstance(row[2], str) and row[2].startswith("AVG_MISMATCH:")
    bad.digest()                                                                          # sentinel is canonicalizable
    assert isinstance(_parse(2.3333333333333335), float)                                  # pre-fix: Decimal(repr(float))
    pre_fix = D(repr(2.3333333333333335)); assert abs(pre_fix - D(7) / 3) > D(1).scaleb(-16) / 2   # why pre-fix failed
    with pytest.raises(CanonicalizationError):
        postprocess(v, s, names, [(1.0, 3, None, None, 0)])                               # float in an int column


def test_regression_3_s5_uses_suffix_bearing_word_terminal_tests():
    from cutwitness.controller import TRIGGERS, _word_test, tester_conformance
    from cutwitness.toyengine import FAULTS
    assert set(TRIGGERS) >= {"F4_MINMAX_EXTREMUM", "F9_LATENT_RESIDUAL"}
    case = _word_test("F9_LATENT_RESIDUAL", 0, "reg3")
    assert case is not None and len(case[3]) > 0, "latent fault test must carry a characterization suffix"
    r = tester_conformance({"tester_conformance": {"correct_histories": 3, "fault_histories": 3,
                                                   "seeded_faults": ["F4_MINMAX_EXTREMUM", "F9_LATENT_RESIDUAL"], "seed": "reg3"}})
    assert r["ok"] and r["detected"]["F4_MINMAX_EXTREMUM"] == 3 and r["detected"]["F9_LATENT_RESIDUAL"] == 3


def test_regression_4_dead_key_suffix_uses_filter_valid_probe():
    from cutwitness.suffix import synthesize
    s = Schema([Table("t0", [("id", "int", False), ("k", "int", False), ("v", "dec", True)], pk=[0])])
    v = View("v", GroupAgg("g", Filter("f", Scan("s", "t0", 3), [(2, "IS NOT NULL", None)]), [1], [("COUNT", None)]))
    h = [Txn({"t0": ZSet([((1, 5, None), 1), ((2, 7, D("1")), 1)])}), Txn({"t0": ZSet([((2, 7, D("1")), -1)])})]
    x = src(s, h)
    first = sorted(x["t0"].d, key=repr)[0]; assert first[2] is None      # pre-fix template (first row) fails the filter
    steps, rec = synthesize(s, v, x, (7,))
    probe = [r for r, m in steps[-1].delta["t0"].items_sorted() if m > 0][0]
    assert probe[1] == 7 and probe[2] is not None


def test_regression_5_s8_witness_closure_is_resumable_per_witness(tmp_path, monkeypatch):
    from cutwitness import controller
    from cutwitness.config import load
    root = os.path.dirname(os.path.dirname(__file__))
    cfg = load(os.path.join(root, "campaign", "CRASHTEST_SIMULATION.yaml"))
    s, v = _avg_view()
    h = [Txn({"t0": ZSet([((1, 3, D("1")), 1)])})]
    unit = {"unit_id": "u", "target": "pg_ivm", "workload": "W3", "tool": "cutwitness_c", "schema": s.to_json(), "views": [v.to_json()],
            "divergences": [{"triage": {"candidate": True, "class": "TARGET_MAINTENANCE_BUG"}, "history_digest": "hd",
                             "history": [e.canon() for e in h], "suffix": [], "obs_digest": "x", "where": "cut"}]}
    first = controller.witness_closure(cfg, str(tmp_path), [unit])
    assert len(first) == 1
    monkeypatch.setattr(controller, "minimize", lambda *a, **k: (_ for _ in ()).throw(AssertionError("recomputed")))
    monkeypatch.setattr(controller, "judge", lambda *a, **k: (_ for _ in ()).throw(AssertionError("re-executed")))
    again = controller.witness_closure(cfg, str(tmp_path), [unit])
    assert [w["id"] for w in again] == [w["id"] for w in first]


def test_regression_6_tlp_secondary_oracle_type_aware_on_text_columns():
    """Found in the clean-state simulation: TLP partitioned text columns with an integer constant."""
    import random
    from cutwitness import w1, w2
    from cutwitness.baselines import b7_tlp, tlp_predicate
    from cutwitness.model import src as _src
    from cutwitness.toyengine import ToyEngine
    from cutwitness.w1fixtures import history as fx
    for sch, vs, h in ((w1.schema(), None, None), (w2.schema(), None, None)):
        if sch.tables.get("stop_times"):
            vs = w1.views(sch); h = w1.diff_transactions(sch, w1.logical_versions([(t, w1.normalize(b, 20, "s")) for t, b in fx()]))
        else:
            vs = w2.views(sch); h = w2.refresh_stream(random.Random(1), sch, 1)
        eng = ToyEngine(sch, vs, "NONE")
        for e in h:
            eng.apply_transaction(e)
        x = _src(sch, h)
        for v in vs:
            if v.exposed():
                col, const = tlp_predicate(v, sch, x)
                assert not b7_tlp(eng.query, v, sch, "duckdb", col, const)["diverges"], v.name
