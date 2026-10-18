"""Semantic transition automata (frozen v1), feasible k-word enumeration and k-transition coverage."""
from __future__ import annotations
from collections import defaultdict
from typing import Dict, List, Set, Tuple
from .model import apply_txn, empty_state, is_txn
from .refmodel import labels_for, touched

STA_VERSION = "sta/1"


def _join_trans(outer: bool):
    up = {"0": ["1", "M"], "1": ["M"], "M": ["M"]}
    down = {"1": ["0"], "M": ["M", "1", "0"]}
    tr = defaultdict(list)
    for l in "01M":
        for r in "01M":
            for side in "LR":
                mine, other = (l, r) if side == "L" else (r, l)
                pf = "p" if other != "0" else "np"
                for nxt in up[mine]:
                    tr[(l + r, f"{side}-ins-{pf}")].append(nxt + r if side == "L" else l + nxt)
                for nxt in down.get(mine, []):
                    tr[(l + r, f"{side}-del-{pf}")].append(nxt + r if side == "L" else l + nxt)
    if not outer:
        return tr
    pad = defaultdict(list)
    for (s, lab), nxts in tr.items():
        for n in nxts:
            p0 = s[0] != "0" and s[1] == "0"; p1 = n[0] != "0" and n[1] == "0"
            pl = "pad-enter" if (p1 and not p0) else ("pad-leave" if (p0 and not p1) else "pad-none")
            pad[(s, pl)].append(n)
    return pad


def _topk_trans(k: int = 2):
    states = list(range(0, k + 2))
    tr = defaultdict(list)
    for n in states:
        nn = min(n + 1, k + 1)
        tr[(n, "enter" if n < k else "enter-evict")].append(nn)
        if n >= k:
            tr[(n, "insert-below")].append(nn)
        if n > 0:
            dn = [n - 1] if n <= k + 0 else [k, k + 1]
            tr[(n, "delete-refill" if n > k else "delete-shrink")].extend(dn)
            if n > k:
                tr[(n, "delete-below")].extend([k, k + 1])
    return tr


AUTOMATA = {
    "GROUP": ("0", {("0", "birth"): ["1"], ("0", "bulk-birth"): ["M"], ("1", "grow"): ["M"], ("M", "grow"): ["M"],
                    ("M", "shrink"): ["M", "1"], ("1", "death"): ["0"], ("M", "bulk-death"): ["0"],
                    ("1", "replace"): ["1"], ("M", "replace"): ["M"]}),
    "MINMAX": ("0", {("0", "birth"): ["U", "T"], ("U", "ext-improve"): ["U", "T"], ("T", "ext-improve"): ["U", "T"],
                     ("U", "ext-tie"): ["T"], ("T", "ext-tie"): ["T"], ("T", "ext-remove-tied"): ["U", "T"],
                     ("U", "ext-remove-unique"): ["U", "T"], ("U", "non-ext"): ["U"], ("T", "non-ext"): ["T"],
                     ("U", "death"): ["0"], ("T", "death"): ["0"], ("0", "non-ext"): ["0"]}),
    "DISTINCT": ("0", {("0", "appear"): ["1", "M"], ("1", "add-dup"): ["M"], ("M", "add-dup"): ["M"],
                       ("M", "remove-dup"): ["M", "1"], ("1", "disappear"): ["0"], ("M", "disappear"): ["0"]}),
    "JOIN": ("00", dict(_join_trans(False))),
    "LEFTJOIN": ("00", dict(_join_trans(True))),
    "TOPK": (0, dict(_topk_trans(2))),
}


def feasible_words(name: str, k: int) -> Set[Tuple[str, ...]]:
    init, tr = AUTOMATA[name]
    reach, frontier = {init}, [init]
    while frontier:
        s = frontier.pop()
        for (a, _), nxts in tr.items():
            if a == s:
                for n in nxts:
                    if n not in reach:
                        reach.add(n); frontier.append(n)
    words = set()

    def walk(s, w):
        if len(w) == k:
            words.add(tuple(w)); return
        for (a, lab), nxts in tr.items():
            if a == s:
                for n in set(nxts):
                    walk(n, w + [lab])
    for s in reach:
        walk(s, [])
    return words


def label_words(schema, views, h) -> Dict[Tuple[str, str, str], List[str]]:
    """Per (op_id, key, automaton) word of base labels along history h (computed on the reference)."""
    from .equivalence import key_canon
    x = empty_state(schema)
    out: Dict[Tuple[str, str, str], List[str]] = defaultdict(list)
    tags: Set[Tuple[str, str, str]] = set()
    for e in h:
        if not is_txn(e):
            continue
        x1 = apply_txn(x, e)
        for v in views:
            ops = {op.nid: op for op in v.ops}
            for (nid, kk), (b, a, d) in touched(v, x, x1).items():
                for aut, lab, tg in labels_for(ops[nid], b, a, d):
                    out[(nid, key_canon(kk), aut)].append(lab)
                    for t in tg:
                        tags.add((aut, lab, t))
        x = x1
    out = dict(out)
    out["__tags__"] = sorted(tags)
    return out


class Coverage:
    def __init__(self, k: int):
        self.k = k
        self.windows: Dict[str, Set[Tuple[str, ...]]] = defaultdict(set)
        self.tags: Set[Tuple[str, str, str]] = set()

    def windows_of(self, words) -> Dict[str, Set[Tuple[str, ...]]]:
        w = defaultdict(set)
        for key, labs in words.items():
            if key == "__tags__":
                continue
            aut = key[2]
            for i in range(len(labs) - self.k + 1):
                w[aut].add(tuple(labs[i: i + self.k]))
        return w

    def novelty(self, words) -> int:
        return sum(len(s - self.windows[a]) for a, s in self.windows_of(words).items())

    def update(self, words) -> int:
        n = 0
        for a, s in self.windows_of(words).items():
            new = s - self.windows[a]; n += len(new); self.windows[a] |= new
        for t in words.get("__tags__", []):
            self.tags.add(tuple(t))
        return n

    def summary(self):
        return {a: len(s) for a, s in sorted(self.windows.items())}
