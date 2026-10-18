"""Context-sensitive logical-key independence I_x and per-key projection equivalence (frozen relation for reduction)."""
from __future__ import annotations
import random
from typing import Dict, List, Tuple
from .model import Life, apply_txn, cjson, crow, empty_state, history_digest, is_txn, sha
from .refmodel import Join, touched


def key_canon(k) -> str:
    return cjson(crow(k if isinstance(k, tuple) else (k,)))


def delta_digest(d) -> str:
    if isinstance(d, tuple):
        return sha([d[0].canon(), d[1].canon()])
    return d.digest()


def annotated_projection(schema, views, h: List) -> Dict[Tuple[str, str], list]:
    x = empty_state(schema)
    lc_so_far: List[str] = []
    seq: Dict[Tuple[str, str], list] = {}
    for e in h:
        if is_txn(e):
            x1 = apply_txn(x, e)
            for v in views:
                for (nid, k), (_, _, d) in touched(v, x, x1).items():
                    kk = (nid, key_canon(k))
                    if kk not in seq:
                        seq[kk] = [["LCPRE", list(lc_so_far)]]
                    seq[kk].append(["D", delta_digest(d)])
            x = x1
        else:
            lc_so_far.append(e.kind)
            for kk in seq:
                seq[kk].append(["L", e.kind])
    return seq


def fingerprint(schema, views, h: List):
    proj = annotated_projection(schema, views, h)
    items = sorted([list(k), v] for k, v in proj.items())
    return sha(items), items


def independent(schema, views, x, t1, t2) -> bool:
    """I_x: disjoint touched (operator, key) sets for every stateful operator at state x."""
    a = set(); b = set()
    for v in views:
        a |= set(touched(v, x, apply_txn(x, t1)))
        b |= set(touched(v, x, apply_txn(x, t2)))
    return not (a & b)


class ClassIndex:
    """Equivalence classes under per-key projection equivalence, with collision fallback to full comparison."""

    def __init__(self, schema, views, rho: float, seed: int):
        self.schema, self.views, self.rho = schema, views, rho
        self.rng = random.Random(seed)
        self.classes: Dict[str, List[dict]] = {}

    def add(self, h: List) -> Tuple[str, bool]:
        fp, items = fingerprint(self.schema, self.views, h)
        bucket = self.classes.setdefault(fp, [])
        for i, c in enumerate(bucket):
            if c["items"] == items:
                c["members"].append(h)
                return f"{fp}:{i}", False
        bucket.append({"items": items, "members": [h]})
        return f"{fp}:{len(bucket) - 1}", True

    def representatives(self):
        out = []
        for fp in sorted(self.classes):
            for i, c in enumerate(self.classes[fp]):
                mem = sorted(c["members"], key=history_digest)
                out.append((f"{fp}:{i}", mem[0], mem[1:]))
        return out

    def noncanonical_sample(self):
        picks = []
        for cid, rep, rest in self.representatives():
            for h in rest:
                if self.rng.random() < self.rho:
                    picks.append((cid, h))
        return picks
