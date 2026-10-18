"""In-process reference IVM target with seeded faults (tester conformance only; never campaign evidence)."""
from __future__ import annotations
import copy, hashlib, itertools
from typing import Dict, List, Optional
from .model import LIFECYCLE_KINDS, Txn, ZSet, apply_txn, empty_state
from .refmodel import Distinct, Filter, GroupAgg, Join, Project, TopK, labels_for, touched, empty_key_state

FAULTS = ["NONE", "F1_WRONG_MULT", "F2_LOST_DELETE", "F3_DUP_INSERT_LATENT", "F4_MINMAX_EXTREMUM",
          "F5_DISTINCT_DUPCOUNT_LATENT", "F6_OUTER_PAD", "F7_TOPK_REFILL", "F8_LIFECYCLE_RESTORE",
          "F9_LATENT_RESIDUAL", "F10_CROSS_KEY_OUT_OF_MODEL", "F11_NONDETERMINISM",
          "N1_ALTERNATING", "N2_PERIODIC", "N3_FIRST_NINE_EQUAL", "N4_BURSTY"]
ADVERSARIAL = {"N1_ALTERNATING": lambda i: i % 2 == 1, "N2_PERIODIC": lambda i: i % 5 == 4,
               "N3_FIRST_NINE_EQUAL": lambda i: i == 9, "N4_BURSTY": lambda i: (i // 3) % 2 == 1}
_ADV_COUNT = {k: 0 for k in ADVERSARIAL}   # execution index per adversarial fault (one engine = one execution)


def reset_adversarial(offset: int = 0):
    for k in _ADV_COUNT:
        _ADV_COUNT[k] = offset
IN_MODEL = {"F1_WRONG_MULT", "F2_LOST_DELETE", "F3_DUP_INSERT_LATENT", "F4_MINMAX_EXTREMUM",
            "F5_DISTINCT_DUPCOUNT_LATENT", "F6_OUTER_PAD", "F7_TOPK_REFILL", "F8_LIFECYCLE_RESTORE",
            "F9_LATENT_RESIDUAL"}
SUPPORTED_LIFECYCLE = {"RESTART", "KILL_RECOVER", "CHECKPOINT", "RESTORE_LATEST", "RESCALE",
                       "REPLACE_VIEW_IDENTICAL", "COMPACT", "UPGRADE"}


_INSTANCE = itertools.count()  # nondeterminism control: hashed coin per (engine instance, read); reproducible per process


class CapabilityResult(Exception):
    pass


def apply_upper(view, z: ZSet) -> ZSet:
    chain = []
    n = view.root
    while n is not view.top:
        chain.append(n); n = n.child
    for node in reversed(chain):
        out = ZSet()
        for r, m in z.d.items():
            if isinstance(node, Filter):
                if node.ok(r):
                    out.add_row(r, m)
            elif isinstance(node, Project):
                out.add_row(node.map(r), m)
        z = out
    return z


class ToyEngine:
    name = "toy-reference-ivm"
    caps = {"ops": {"group", "distinct", "topk", "join", "leftjoin"}, "lifecycle": SUPPORTED_LIFECYCLE}

    def __init__(self, schema, views, fault: str = "NONE"):
        if fault not in FAULTS:
            raise ValueError(fault)
        self.schema, self.views, self.fault = schema, views, fault
        self.x = empty_state(schema)
        self.ks: Dict[str, Dict] = {v.name: {} for v in views}
        self.resid: Dict[str, Dict] = {v.name: {} for v in views}
        self.padflag: Dict[str, set] = {v.name: set() for v in views}
        self.log: List[Txn] = []
        self.ckpt = None
        self._inst = next(_INSTANCE); self._reads = 0
        self._adv = None
        if fault in ADVERSARIAL:
            self._adv = ADVERSARIAL[fault](_ADV_COUNT[fault]); _ADV_COUNT[fault] += 1

    # -- adapter contract
    def probe_capabilities(self):
        return {"target": self.name, "ops": sorted(self.caps["ops"]), "lifecycle": sorted(self.caps["lifecycle"])}

    def apply_transaction(self, t: Txn):
        x1 = apply_txn(self.x, t)
        for v in self.views:
            top = v.top
            st = self.ks[v.name]
            for (nid, key), (b, a, d) in touched(v, self.x, x1).items():
                if nid != top.nid:
                    continue
                labs = {aut: lab for aut, lab, _ in labels_for(top, b, a, d)}
                self._update(v, st, key, d, labs)
        self.x = x1
        self.log.append(t)

    def _add(self, st, key, d):
        cur = st.get(key)
        if isinstance(d, tuple):
            cur = cur if cur is not None else (ZSet(), ZSet())
            st[key] = (cur[0] + d[0], cur[1] + d[1])
        else:
            st[key] = (cur if cur is not None else ZSet()) + d

    def _update(self, v, st, key, d, labs):
        f = self.fault
        g = labs.get("GROUP"); mm = labs.get("MINMAX"); ds = labs.get("DISTINCT"); tk = labs.get("TOPK"); lj = labs.get("LEFTJOIN")
        if f == "F1_WRONG_MULT" and g == "grow" and st.get(key, ZSet()).total() == 1:
            self._add(st, key, d); self._add(st, key, d); return
        if f == "F2_LOST_DELETE" and g == "shrink" and st.get(key, ZSet()).total() == 2:
            return
        if f == "F3_DUP_INSERT_LATENT" and ds == "appear":
            self._add(st, key, d); self._add(st, key, d); return
        if f == "F4_MINMAX_EXTREMUM" and mm == "ext-remove-unique":
            return
        if f == "F5_DISTINCT_DUPCOUNT_LATENT" and ds == "add-dup":
            return
        if f == "F6_OUTER_PAD" and lj == "pad-enter":
            self.padflag[v.name].add(key)
        if f == "F6_OUTER_PAD" and lj == "pad-leave":
            self.padflag[v.name].discard(key)
        if f == "F9_LATENT_RESIDUAL" and g in ("birth", "bulk-birth") and key in self.resid[v.name]:
            self._add(st, key, self.resid[v.name].pop(key))
        if f == "F9_LATENT_RESIDUAL" and g in ("death", "bulk-death"):
            phantom = next(iter(sorted(st.get(key, ZSet()).d, key=repr)), None)
            if phantom is not None:
                self.resid[v.name][key] = ZSet([(phantom, 1)])
        self._add(st, key, d)
        if f == "F7_TOPK_REFILL" and tk == "delete-refill":
            bag = st[key]
            ranked = v.top.ranked(bag)
            if len(ranked) >= v.top.k:
                st[key] = bag + ZSet([(ranked[v.top.k - 1], -1)])
        if f == "F10_CROSS_KEY_OUT_OF_MODEL" and len(st) >= 3 and not isinstance(d, tuple):
            others = sorted((k for k in st if k != key and st[k].total() >= 2), key=repr)
            if others:
                o = others[0]; r = next(iter(st[o].d)); st[o] = st[o] + ZSet([(r, -1)])

    def read_views(self) -> Dict[str, ZSet]:
        out = {}
        self._reads += 1
        phantom = self.fault == "F11_NONDETERMINISM" and hashlib.sha256(f"{self._inst}:{self._reads}".encode()).digest()[0] & 1 == 1
        for v in self.views:
            z = ZSet()
            top = v.top
            for key, s in self.ks[v.name].items():
                ko = top.key_output(key, s)
                if self.fault == "F6_OUTER_PAD" and key in self.padflag[v.name] and isinstance(top, Join):
                    ko = ko.filter(lambda r, n=top.left.arity: any(x is not None for x in r[n:]))
                z = z + ko
            z = apply_upper(v, z)
            if phantom or self._adv:
                z = z + ZSet([(tuple(["~"] * top.arity), 1)])
            out[v.name] = z
        return out

    def flush(self):
        return True

    def lifecycle(self, kind: str):
        if kind not in self.caps["lifecycle"]:
            raise CapabilityResult(f"lifecycle {kind} unsupported by {self.name}")
        if kind in ("RESTART", "KILL_RECOVER"):
            self.ks = copy.deepcopy(self.ks)
            if self.fault == "F8_LIFECYCLE_RESTORE":
                for v in self.views:
                    if isinstance(v.top, GroupAgg):
                        self.ks[v.name] = {k: s for k, s in self.ks[v.name].items() if s.total() != 1}
        elif kind == "CHECKPOINT":
            self.ckpt = (copy.deepcopy(self.ks), dict(self.x), len(self.log), copy.deepcopy(self.resid), copy.deepcopy(self.padflag))
        elif kind == "RESTORE_LATEST":
            log = list(self.log)
            if self.ckpt is None:
                fresh = ToyEngine(self.schema, self.views, self.fault)
                for t in log:
                    fresh.apply_transaction(t)
            else:
                ks, x, n, resid, pad = self.ckpt
                fresh = ToyEngine(self.schema, self.views, self.fault)
                fresh.ks, fresh.x, fresh.resid, fresh.padflag = copy.deepcopy(ks), dict(x), copy.deepcopy(resid), copy.deepcopy(pad)
                fresh.log = log[:n]
                for t in log[n:]:
                    fresh.apply_transaction(t)
                fresh.ckpt = self.ckpt
            self.__dict__.update(fresh.__dict__)
        elif kind == "COMPACT":
            for v in self.views:
                self.ks[v.name] = {k: s for k, s in self.ks[v.name].items()
                                   if ((s[0] or s[1]) if isinstance(s, tuple) else bool(s))}
        elif kind in ("RESCALE", "REPLACE_VIEW_IDENTICAL", "UPGRADE"):
            self.ks = copy.deepcopy(self.ks)

    def clean_rebuild(self, x) -> Dict[str, ZSet]:
        fresh = ToyEngine(self.schema, self.views, "NONE" if self.fault == "F11_NONDETERMINISM" else self.fault)
        fresh.apply_transaction(Txn({t: z for t, z in x.items()}))
        return fresh.read_views()

    def snapshot(self):
        return copy.deepcopy(self)

    def destroy(self):
        return None

    def query(self, sql: str):
        import duckdb
        from .targetsql import ddl
        con = duckdb.connect()
        try:
            for st in ddl(self.schema, "duckdb"):
                con.execute(st)
            for t in self.schema.order:
                for r, m in self.x[t].items_sorted():
                    for _ in range(m):
                        con.execute(f"INSERT INTO {t} VALUES ({', '.join('?' for _ in r)})", list(r))
            return con.execute(sql).fetchall()
        finally:
            con.close()
