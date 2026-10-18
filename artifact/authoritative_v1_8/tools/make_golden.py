"""Regenerate golden protocol logs (run only when an adapter's wire behaviour is intentionally changed)."""
import json, os, random, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
from conftest import mock_sessions
from cutwitness.w3 import gen_history


def capture():
    m = mock_sessions(1); h = gen_history(random.Random(1), m["schema"], 4); out = {}
    mk, pg, dpg = m["pg"]; pg.log.clear(); a = mk("golden")
    for t in h: a.apply_transaction(t)
    a.read_views(); a.lifecycle("RESTART"); a.lifecycle("COMPACT")
    out["pg_ivm_sql"] = list(pg.log); out["pg_ivm_docker"] = [c for c in dpg.log]
    mk, rw, drw = m["rw"]; rw.log.clear(); b = mk("golden")
    for t in h: b.apply_transaction(t)
    b.read_views(); b.lifecycle("RESCALE"); b.lifecycle("KILL_RECOVER")
    out["risingwave_sql"] = list(rw.log); out["risingwave_docker"] = [c for c in drw.log]
    mk, fm = m["fe"]; fm.log.clear(); c = mk("golden")
    for t in h: c.apply_transaction(t)
    c.read_views(); c.lifecycle("CHECKPOINT"); c.lifecycle("RESTART")
    out["feldera_http"] = [[x[0], x[1], x[2]] for x in fm.log]
    return out


if __name__ == "__main__":
    json.dump(capture(), open(os.path.join(ROOT, "tests", "fixtures", "golden_protocol_logs.json"), "w"), indent=0, sort_keys=True)
    print("golden logs written")
