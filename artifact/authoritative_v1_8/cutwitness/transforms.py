"""Terminal-state-preserving history transformations, lifecycle insertion and continuations, with proof records."""
from __future__ import annotations
from typing import List
from .model import (Life, Txn, ZSet, history_digest, is_txn, prefix_legal, src, state_digest)

CLASS = {
    "reorder": "SOUND_TERMINAL_EQUIVALENCE", "split": "SOUND_TERMINAL_EQUIVALENCE",
    "coalesce": "SOUND_TERMINAL_EQUIVALENCE", "inverse_detour": "SOUND_TERMINAL_EQUIVALENCE",
    "recurrence_detour": "SOUND_TERMINAL_EQUIVALENCE", "insert_lifecycle": "LIFECYCLE_INSERTION",
    "move_lifecycle": "LIFECYCLE_INSERTION", "seed_diversify": "HEURISTIC_TEST_MUTATION",
    "append_continuation": "CONTINUATION",
}


class IllegalTransform(Exception):
    pass


def _proof(schema, name, params, h0, h1, require_equal: bool) -> dict:
    ok, idx, why = prefix_legal(schema, h1)
    if not ok:
        raise IllegalTransform(f"{name}: prefix {idx} illegal: {why}")
    s0, s1 = state_digest(src(schema, h0)), state_digest(src(schema, h1))
    if require_equal and s0 != s1:
        raise IllegalTransform(f"{name}: terminal source state changed")
    return {"transform": name, "class": CLASS[name], "params": params,
            "history_before": history_digest(h0), "history_after": history_digest(h1),
            "src_before": s0, "src_after": s1, "prefix_legal": True, "terminal_equal": s0 == s1}


def reorder(schema, h: List, i: int):
    if not (0 <= i < len(h) - 1 and is_txn(h[i]) and is_txn(h[i + 1])):
        raise IllegalTransform("reorder needs two adjacent transactions")
    h1 = h[:i] + [h[i + 1], h[i]] + h[i + 2:]
    return h1, _proof(schema, "reorder", {"i": i}, h, h1, True)


def split(schema, h: List, i: int, part_idx: List[int]):
    if not is_txn(h[i]):
        raise IllegalTransform("split needs a transaction")
    rows = list(h[i].rows())
    sel = set(part_idx)
    if not sel or len(sel) >= len(rows):
        raise IllegalTransform("split needs a proper non-empty part")
    a, b = {}, {}
    for j, (t, r, m) in enumerate(rows):
        (a if j in sel else b).setdefault(t, ZSet()).add_row(r, m)
    for first, second in ((Txn(a), Txn(b)), (Txn(b), Txn(a))):
        h1 = h[:i] + [first, second] + h[i + 1:]
        try:
            return h1, _proof(schema, "split", {"i": i, "part": sorted(sel)}, h, h1, True)
        except IllegalTransform:
            continue
    raise IllegalTransform("split: no legal order")


def coalesce(schema, h: List, i: int):
    if not (0 <= i < len(h) - 1 and is_txn(h[i]) and is_txn(h[i + 1])):
        raise IllegalTransform("coalesce needs two adjacent transactions")
    d = {}
    for e in (h[i], h[i + 1]):
        for t, z in e.delta.items():
            d[t] = d.get(t, ZSet()) + z
    merged = Txn(d)
    h1 = h[:i] + ([merged] if not merged.is_empty() else []) + h[i + 2:]
    return h1, _proof(schema, "coalesce", {"i": i}, h, h1, True)


def inverse_detour(schema, h: List, i: int, t: Txn):
    h1 = h[: i + 1] + [t, t.inverse()] + h[i + 1:]
    return h1, _proof(schema, "inverse_detour", {"i": i, "txn": t.canon()}, h, h1, True)


def recurrence_detour(schema, h: List, i: int, j: int):
    tx = [e for e in h[: i + 1] if is_txn(e)][-j:] if j > 0 else []
    if len(tx) != j or j == 0:
        raise IllegalTransform("recurrence detour needs j earlier transactions")
    detour = [e.inverse() for e in reversed(tx)] + list(tx)
    h1 = h[: i + 1] + detour + h[i + 1:]
    return h1, _proof(schema, "recurrence_detour", {"i": i, "j": j}, h, h1, True)


def insert_lifecycle(schema, h: List, i: int, kind: str):
    h1 = h[: i + 1] + [Life(kind)] + h[i + 1:]
    return h1, _proof(schema, "insert_lifecycle", {"i": i, "kind": kind}, h, h1, True)


def move_lifecycle(schema, h: List, src_i: int, dst_i: int):
    if not isinstance(h[src_i], Life):
        raise IllegalTransform("move_lifecycle needs a lifecycle event")
    ev = h[src_i]
    rest = h[:src_i] + h[src_i + 1:]
    dst = min(max(dst_i, -1), len(rest) - 1)
    h1 = rest[: dst + 1] + [ev] + rest[dst + 1:]
    return h1, _proof(schema, "move_lifecycle", {"from": src_i, "to": dst_i}, h, h1, True)


def seed_diversify(schema, h: List, i: int, t: Txn):
    h1 = h[: i + 1] + [t] + h[i + 1:]
    return h1, _proof(schema, "seed_diversify", {"i": i, "txn": t.canon()}, h, h1, False)


def append_continuation(schema, h: List, suffix: List):
    h1 = list(h) + list(suffix)
    return h1, _proof(schema, "append_continuation", {"len": len(suffix)}, h, h1, False)
