"""Amendment v1.2: latent attribution separates history-conditioned latent state from continuation-triggered failures."""
import csv, json, os, random, subprocess, sys
from decimal import Decimal as D
import pytest
from cutwitness.attribution import attribute, attribution_closure, fresh_load
from cutwitness.model import Schema, Table, Txn, ZSet, history_canon, src
from cutwitness.refmodel import GroupAgg, Scan, View
from cutwitness.toyengine import ToyEngine, reset_adversarial

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = Schema([Table("t0", [("id", "int", False), ("k", "int", False), ("v", "dec", True)], pk=[0])])
V = View("v", GroupAgg("g", Scan("s", "t0", 3), [1], [("COUNT", None), ("SUM", 2)]))
ins = lambda *rows: Txn({"t0": ZSet([(r, 1) for r in rows])})
dele = lambda *rows: Txn({"t0": ZSet([(r, -1) for r in rows])})


def _latent_case(fault):
    """Search for a (history, suffix) that is latent on the history path for this toy fault (deterministic scan)."""
    from cutwitness.oracles import judge
    from cutwitness.suffix import synthesize
    cands = [[ins((1, 7, D(5))), dele((1, 7, D(5)))],
             [ins((1, 7, D(5)), (2, 7, D(3))), dele((1, 7, D(5)))],
             [ins((1, 7, D(5)), (2, 7, D(3)))]]
    for h in cands:
        x = src(S, h)
        suffix, _ = synthesize(S, V, x, (7,))
        v = judge(lambda: ToyEngine(S, [V], fault), S, [V], h, suffix, use_o3=False)
        if v["diverges"] and str(v.get("where", "")).startswith("suffix"):
            return h, suffix
    return None


def test_history_conditioned_latent_residual():
    case = _latent_case("F9_LATENT_RESIDUAL")
    assert case is not None
    r = attribute(lambda: ToyEngine(S, [V], "F9_LATENT_RESIDUAL"), S, [V], case[0], case[1], 10)
    assert r["attribution_class"] == "HISTORY_CONDITIONED_LATENT", r
    assert r["history_path_result"].startswith("FC_PASS;CONTINUATION_FAIL") and r["fresh_cut_result"] == "FC_PASS;CONTINUATION_PASS"


def test_continuation_triggered_delete_path_defect():
    case = _latent_case("F2_LOST_DELETE")
    assert case is not None
    r = attribute(lambda: ToyEngine(S, [V], "F2_LOST_DELETE"), S, [V], case[0], case[1], 10)
    assert r["attribution_class"] == "CONTINUATION_TRIGGERED", r
    assert r["fresh_cut_result"].startswith("FC_PASS;CONTINUATION_FAIL")


def test_nondeterministic_replay_is_unresolved():
    case = _latent_case("F9_LATENT_RESIDUAL")
    reset_adversarial(0)
    r = attribute(lambda: ToyEngine(S, [V], "N1_ALTERNATING"), S, [V], case[0], case[1], 10)
    assert r["attribution_class"] == "UNRESOLVED_ATTRIBUTION"


def test_correct_engine_is_unresolved_not_latent():
    case = _latent_case("F9_LATENT_RESIDUAL")
    r = attribute(lambda: ToyEngine(S, [V], "NONE"), S, [V], case[0], case[1], 3)
    assert r["attribution_class"] == "UNRESOLVED_ATTRIBUTION" and "not latent" in r["reason"]


def test_fresh_load_is_exactly_the_final_cut_without_lifecycle():
    from cutwitness.model import Life
    h = [ins((1, 7, D(5)), (2, 3, D(1))), Life("RESTART"), dele((1, 7, D(5)))]
    fl = fresh_load(S, h)
    assert len(fl) == 1 and src(S, fl) == src(S, h)


def test_attribution_is_deterministic_and_resumable(tmp_path, monkeypatch):
    from cutwitness import attribution as A
    from cutwitness.controller import make_factory
    from cutwitness.config import load
    case = _latent_case("F9_LATENT_RESIDUAL")
    cfg = load(os.path.join(ROOT, "campaign", "CRASHTEST_SIMULATION.yaml")); cfg["targets"]["pg_ivm"]["fault"] = "F9_LATENT_RESIDUAL"
    w = {"id": "w1", "target": "pg_ivm", "workload": "W3", "status": "NEW", "latent": True, "schema": S.to_json(), "views": [V.to_json()],
         "original_history": history_canon(case[0]), "original_suffix": history_canon(case[1])}
    a = attribution_closure(cfg, str(tmp_path / "a"), [w], make_factory)
    b = attribution_closure(cfg, str(tmp_path / "b"), [w], make_factory)
    assert a == b and a["w1"]["attribution_class"] == "HISTORY_CONDITIONED_LATENT"
    monkeypatch.setattr(A, "attribute", lambda *x, **k: (_ for _ in ()).throw(AssertionError("recomputed")))
    assert attribution_closure(cfg, str(tmp_path / "a"), [w], make_factory) == a
    nonlatent = dict(w, id="w2", latent=False)
    assert "w2" not in attribution_closure(cfg, str(tmp_path / "c"), [nonlatent], make_factory)


def test_campaign_emits_latent_attribution_csv(tmp_path):
    d = str(tmp_path / "run")
    assert subprocess.run([sys.executable, "-m", "cutwitness.one_shot", "--config", os.path.join(ROOT, "campaign", "CRASHTEST_SIMULATION.yaml"),
                           "--run-dir", d], cwd=ROOT, capture_output=True).returncode == 0
    p = os.path.join(d, "analysis", "SYNTHETIC_ENGINEERING", "latent_attribution.csv")
    rows = list(csv.DictReader(open(p)))
    assert rows, "the crash-test campaign's latent fault must produce attributed latent witnesses"
    assert all(r["attribution_class"] in ("HISTORY_CONDITIONED_LATENT", "CONTINUATION_TRIGGERED", "UNRESOLVED_ATTRIBUTION") for r in rows)
    ws = list(csv.DictReader(open(os.path.join(d, "analysis", "SYNTHETIC_ENGINEERING", "adjudication_worksheet.csv"))))
    assert all(r["latent_attribution"] for r in ws)
