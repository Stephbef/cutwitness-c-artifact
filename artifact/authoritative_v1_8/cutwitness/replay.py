"""One-command witness replay: python -m cutwitness.replay <witness.json>"""
from __future__ import annotations
import json, sys
from .model import history_from_canon, sha
from .oracles import judge
from .serialize import schema_from_json, views_from_json
from .toyengine import ToyEngine

ADAPTERS = {"toy-reference-ivm": ToyEngine}


def replay(path: str) -> dict:
    w = json.load(open(path))
    schema = schema_from_json(w["schema"]); views = views_from_json(schema, w["views"])
    if w["target"] not in ADAPTERS:
        return {"reproduced": False, "reason": f"adapter {w['target']} not available in this package"}
    h = history_from_canon(w["history"]); s = history_from_canon(w["suffix"])
    fac = lambda: ADAPTERS[w["target"]](schema, views, w.get("target_fault", "NONE"))
    v = judge(fac, schema, views, h, s)
    return {"reproduced": bool(v["diverges"]), "where": v.get("where"), "o3_agree": v.get("o3_agree")}


if __name__ == "__main__":
    r = replay(sys.argv[1]); print(json.dumps(r, sort_keys=True)); sys.exit(0 if r["reproduced"] else 1)
