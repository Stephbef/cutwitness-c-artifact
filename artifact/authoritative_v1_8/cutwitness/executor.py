"""Prefix-trie executor: shares common prefixes via target snapshot/fork; falls back to replay without fork."""
from __future__ import annotations
from typing import Callable, Dict, List
from .model import cjson, is_txn, sha
from .oracles import obs_digest


def _run_event(eng, e):
    if is_txn(e):
        eng.apply_transaction(e)
    else:
        eng.lifecycle(e.kind)


def trie_execute(factory: Callable, histories: List[List]) -> Dict[int, str]:
    """Return {history index: observation digest at its end}; one engine step per distinct trie node."""
    root: dict = {"children": {}, "ends": []}
    for idx, h in enumerate(histories):
        node = root
        for e in h:
            key = sha(e.canon())
            node = node["children"].setdefault(key, {"event": e, "children": {}, "ends": []})
        node["ends"].append(idx)
    out: Dict[int, str] = {}
    steps = [0]
    probe = factory()
    can_fork = hasattr(probe, "snapshot")

    def walk(node, eng, prefix):
        if node["ends"]:
            eng.flush(); d = obs_digest(eng.read_views())
            for i in node["ends"]:
                out[i] = d
        kids = list(node["children"].values())
        for j, ch in enumerate(kids):
            if j < len(kids) - 1:
                if can_fork:
                    e2 = eng.snapshot()
                else:
                    e2 = factory()
                    for ev in prefix:
                        _run_event(e2, ev)
            else:
                e2 = eng
            _run_event(e2, ch["event"]); steps[0] += 1
            walk(ch, e2, prefix + [ch["event"]])
    walk(root, probe, [])
    out["__steps__"] = steps[0]
    return out


def plain_execute(factory: Callable, histories: List[List]) -> Dict[int, str]:
    out = {}; steps = 0
    for i, h in enumerate(histories):
        eng = factory()
        for e in h:
            _run_event(eng, e); steps += 1
        eng.flush(); out[i] = obs_digest(eng.read_views())
    out["__steps__"] = steps
    return out
