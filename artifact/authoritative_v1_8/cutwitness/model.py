"""Exact typed rows, Z-sets, schema constraints, events, histories and canonical digests."""
from __future__ import annotations
import hashlib, json
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

Row = Tuple[Any, ...]
COL_TYPES = ("int", "dec", "text")
LIFECYCLE_KINDS = ("RESTART", "KILL_RECOVER", "CHECKPOINT", "RESTORE_LATEST", "RESCALE",
                   "UPGRADE", "REPLACE_VIEW_IDENTICAL", "COMPACT")


def cval(v: Any):
    if v is None:
        return None
    if isinstance(v, bool):
        raise TypeError("bool is not a supported exact type")
    if isinstance(v, int):
        return ["i", str(v)]
    if isinstance(v, Decimal):
        if not v.is_finite():
            raise TypeError("non-finite decimal")
        s = format(v.normalize(), "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        if s in ("-0", "", "-"):
            s = "0"
        return ["d", s]
    if isinstance(v, str):
        return ["s", v]
    raise TypeError(f"unsupported value type {type(v).__name__}")


def crow(r: Row) -> list:
    return [cval(v) for v in r]


def cjson(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha(obj) -> str:
    return hashlib.sha256(cjson(obj).encode()).hexdigest()


def row_key(r: Row) -> str:
    return cjson(crow(r))


class ZSet:
    """Finite map row -> nonzero integer multiplicity."""
    __slots__ = ("d",)

    def __init__(self, items=None):
        self.d: Dict[Row, int] = {}
        if items is not None:
            it = items.items() if isinstance(items, dict) else items
            for r, m in it:
                self.add_row(tuple(r), int(m))

    def add_row(self, r: Row, m: int) -> None:
        if m == 0:
            return
        n = self.d.get(r, 0) + m
        if n:
            self.d[r] = n
        else:
            self.d.pop(r, None)

    def copy(self) -> "ZSet":
        z = ZSet(); z.d = dict(self.d); return z

    def __add__(self, o: "ZSet") -> "ZSet":
        z = self.copy()
        for r, m in o.d.items():
            z.add_row(r, m)
        return z

    def __neg__(self) -> "ZSet":
        z = ZSet(); z.d = {r: -m for r, m in self.d.items()}; return z

    def __sub__(self, o: "ZSet") -> "ZSet":
        return self + (-o)

    def __eq__(self, o) -> bool:
        return isinstance(o, ZSet) and self.d == o.d

    __hash__ = None

    def __len__(self) -> int:
        return len(self.d)

    def __bool__(self) -> bool:
        return bool(self.d)

    def items_sorted(self) -> List[Tuple[Row, int]]:
        return sorted(self.d.items(), key=lambda kv: row_key(kv[0]))

    def is_nonneg(self) -> bool:
        return all(m > 0 for m in self.d.values())

    def total(self) -> int:
        return sum(self.d.values())

    def canon(self) -> list:
        return [[crow(r), m] for r, m in self.items_sorted()]

    def digest(self) -> str:
        return sha(self.canon())

    def filter(self, pred) -> "ZSet":
        z = ZSet(); z.d = {r: m for r, m in self.d.items() if pred(r)}; return z

    def has_pos_and_neg(self) -> bool:
        return any(m > 0 for m in self.d.values()) and any(m < 0 for m in self.d.values())

    def __repr__(self) -> str:
        return f"ZSet({self.items_sorted()})"


class Table:
    def __init__(self, name: str, cols, pk=None, fks=()):
        self.name = name
        self.cols = [tuple(c) for c in cols]  # (name, type, nullable)
        for _, t, _ in self.cols:
            if t not in COL_TYPES:
                raise ValueError(f"unsupported column type {t}")
        self.pk = tuple(pk) if pk is not None else None
        self.fks = [(tuple(c), parent, tuple(pc)) for c, parent, pc in fks]

    @property
    def arity(self) -> int:
        return len(self.cols)

    def to_json(self) -> dict:
        return {"name": self.name, "cols": [list(c) for c in self.cols],
                "pk": list(self.pk) if self.pk is not None else None,
                "fks": [[list(c), p, list(pc)] for c, p, pc in self.fks]}


class Schema:
    def __init__(self, tables: List[Table]):
        self.tables = {t.name: t for t in tables}
        self.order = [t.name for t in tables]

    def to_json(self) -> dict:
        return {"tables": [self.tables[n].to_json() for n in self.order]}

    def digest(self) -> str:
        return sha(self.to_json())

    def children_of(self, parent: str):
        for t in self.order:
            for c, p, pc in self.tables[t].fks:
                if p == parent:
                    yield t, c, pc


def type_ok(v, t: str, nullable: bool) -> bool:
    if v is None:
        return nullable
    if t == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "dec":
        return isinstance(v, Decimal)
    return isinstance(v, str)


State = Dict[str, ZSet]


def empty_state(schema: Schema) -> State:
    return {n: ZSet() for n in schema.order}


def state_digest(state: State) -> str:
    return sha({t: state[t].canon() for t in sorted(state)})


def legal_state(schema: Schema, state: State) -> Tuple[bool, str]:
    for name in schema.order:
        tb = schema.tables[name]
        z = state[name]
        seen = set()
        for r, m in z.d.items():
            if m < 0:
                return False, f"negative multiplicity in {name}"
            if len(r) != tb.arity:
                return False, f"arity mismatch in {name}"
            for v, (_, t, nl) in zip(r, tb.cols):
                if not type_ok(v, t, nl):
                    return False, f"type/null violation in {name}"
            if tb.pk is not None:
                if m != 1:
                    return False, f"duplicate row in keyed table {name}"
                k = tuple(r[i] for i in tb.pk)
                if k in seen:
                    return False, f"primary key violation in {name}"
                seen.add(k)
    for name in schema.order:
        tb = schema.tables[name]
        for cols, parent, pcols in tb.fks:
            pvals = {tuple(r[i] for i in pcols) for r in state[parent].d}
            for r in state[name].d:
                v = tuple(r[i] for i in cols)
                if any(x is None for x in v):
                    continue
                if v not in pvals:
                    return False, f"foreign key violation {name}->{parent}"
    return True, "ok"


class Txn:
    __slots__ = ("delta",)

    def __init__(self, delta: Dict[str, ZSet]):
        self.delta = {t: z for t, z in delta.items() if z}

    def canon(self) -> dict:
        return {"t": "txn", "d": {t: self.delta[t].canon() for t in sorted(self.delta)}}

    def inverse(self) -> "Txn":
        return Txn({t: -z for t, z in self.delta.items()})

    def is_empty(self) -> bool:
        return not self.delta

    def size(self) -> int:
        return sum(len(z) for z in self.delta.values())

    def rows(self):
        for t in sorted(self.delta):
            for r, m in self.delta[t].items_sorted():
                yield t, r, m


class Life:
    __slots__ = ("kind",)

    def __init__(self, kind: str):
        if kind not in LIFECYCLE_KINDS:
            raise ValueError(f"unknown lifecycle kind {kind}")
        self.kind = kind

    def canon(self) -> dict:
        return {"t": "lc", "k": self.kind}


def is_txn(e) -> bool:
    return isinstance(e, Txn)


def apply_txn(state: State, txn: Txn) -> State:
    new = dict(state)
    for t, z in txn.delta.items():
        new[t] = state[t] + z
    return new


def src(schema: Schema, h: List) -> State:
    x = empty_state(schema)
    for e in h:
        if is_txn(e):
            x = apply_txn(x, e)
    return x


def prefix_legal(schema: Schema, h: List, base: Optional[State] = None) -> Tuple[bool, int, str]:
    x = base if base is not None else empty_state(schema)
    for i, e in enumerate(h):
        if is_txn(e):
            x = apply_txn(x, e)
            ok, why = legal_state(schema, x)
            if not ok:
                return False, i, why
    return True, -1, "ok"


def event_canon(e) -> dict:
    return e.canon()


def history_canon(h: List) -> list:
    return [e.canon() for e in h]


def history_digest(h: List) -> str:
    return sha(history_canon(h))


def event_from_canon(c: dict):
    if c["t"] == "lc":
        return Life(c["k"])
    return Txn({t: ZSet((tuple(uncval(v) for v in r), m) for r, m in rows) for t, rows in c["d"].items()})


def uncval(v):
    if v is None:
        return None
    tag, s = v
    if tag == "i":
        return int(s)
    if tag == "d":
        return Decimal(s)
    return s


def history_from_canon(c: list) -> List:
    return [event_from_canon(e) for e in c]
