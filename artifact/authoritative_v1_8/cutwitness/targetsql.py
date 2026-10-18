"""Flat target SQL (aliased, dialect-aware) with declared output types and exact AVG companions."""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_EVEN
from typing import List, Tuple
from .model import ZSet
from .refmodel import (AVG_Q, Distinct, Filter, GroupAgg, Join, LeftJoin, Project, Scan, TopK, UnsupportedSemantics,
                       View, sql_lit)

DIALECTS = ("postgres", "risingwave", "feldera", "duckdb")


def col_types(node, schema) -> List[str]:
    """Declared output type per column: int | dec | text."""
    if isinstance(node, Scan):
        return [t for _, t, _ in schema.tables[node.table].cols]
    if isinstance(node, Filter):
        return col_types(node.child, schema)
    if isinstance(node, Project):
        ct = col_types(node.child, schema); return [ct[i] for i in node.cols]
    if isinstance(node, Join):
        return col_types(node.left, schema) + col_types(node.right, schema)
    if isinstance(node, GroupAgg):
        ct = col_types(node.child, schema); out = [ct[i] for i in node.gcols]
        for fn, c in node.aggs:
            out.append("int" if fn == "COUNT" else ("dec" if fn == "AVG" else ct[c]))
        return out
    if isinstance(node, (Distinct, TopK)):
        return col_types(node.child, schema)
    raise UnsupportedSemantics(type(node).__name__)


def _linear(node):
    """(table, alias-free column expressions list, predicate list) for Scan/Filter/Project chains."""
    if isinstance(node, Scan):
        return node.table, [f"c{i}" for i in range(node.arity)], []
    if isinstance(node, Filter):
        t, cols, preds = _linear(node.child)
        for c, op, k in node.preds:
            e = cols[c]
            preds.append(f"{e} {op}" if op in ("IS NULL", "IS NOT NULL") else f"{e} {op} {sql_lit(k)}")
        return t, cols, preds
    if isinstance(node, Project):
        t, cols, preds = _linear(node.child)
        return t, [cols[i] for i in node.cols], preds
    return None


def _from_clause(node) -> Tuple[str, List[str], List[str]]:
    """FROM clause, output column expressions, WHERE predicates for linear subtrees or one equi-join."""
    lin = _linear(node)
    if lin is not None:
        t, cols, preds = lin
        return f"{t} AS q0", [f"q0.{c}" for c in cols], [_q(p, "q0") for p in preds]
    if isinstance(node, Join):
        l, r = _linear(node.left), _linear(node.right)
        if l is None or r is None:
            raise UnsupportedSemantics("flat SQL needs linear join inputs")
        lc = [f"ql.{c}" for c in l[1]]; rc = [f"qr.{c}" for c in r[1]]
        on = [f"{lc[node.lk]} = {rc[node.rk]}"] + [_q(p, "qr") for p in r[2]]
        where = [_q(p, "ql") for p in l[2]]
        if not node.outer:
            where += [_q(p, "qr") for p in r[2]]; on = on[:1]
        jt = "LEFT JOIN" if node.outer else "JOIN"
        return f"{l[0]} AS ql {jt} {r[0]} AS qr ON " + " AND ".join(on), lc + rc, where
    raise UnsupportedSemantics("not flattenable")


def _q(pred: str, alias: str) -> str:
    return alias + "." + pred


def target_sql(view: View, schema, dialect: str) -> Tuple[str, List[str]]:
    """Return (SELECT text, physical column names). AVG(c) becomes avg, sum, count columns."""
    if dialect not in DIALECTS:
        raise ValueError(dialect)
    root = view.root
    while isinstance(root, (Filter, Project)) and root is not view.top:
        raise UnsupportedSemantics("operators above the top stateful operator are out of the target subset")
    top = view.top
    if isinstance(top, GroupAgg):
        frm, cols, where = _from_clause(top.child)
        sel, names = [], []
        for j, g in enumerate(top.gcols):
            sel.append(f"{cols[g]} AS c{j}"); names.append(f"c{j}")
        base = len(top.gcols)
        for j, (fn, c) in enumerate(top.aggs):
            n = f"c{base + j}"
            if fn == "COUNT":
                sel.append(f"COUNT({'*' if c is None else cols[c]}) AS {n}"); names.append(n)
            elif fn == "AVG":
                sel += [f"AVG({cols[c]}) AS {n}", f"SUM({cols[c]}) AS {n}_s", f"COUNT({cols[c]}) AS {n}_n"]
                names += [n, f"{n}_s", f"{n}_n"]
            else:
                sel.append(f"{fn}({cols[c]}) AS {n}"); names.append(n)
        sql = f"SELECT {', '.join(sel)} FROM {frm}" + (f" WHERE {' AND '.join(where)}" if where else "")
        return sql + " GROUP BY " + ", ".join(cols[g] for g in top.gcols), names
    if isinstance(top, Distinct):
        frm, cols, where = _from_clause(top.child)
        names = [f"c{i}" for i in range(len(cols))]
        return (f"SELECT DISTINCT {', '.join(f'{c} AS {n}' for c, n in zip(cols, names))} FROM {frm}"
                + (f" WHERE {' AND '.join(where)}" if where else "")), names
    if isinstance(top, Join):
        frm, cols, where = _from_clause(top)
        names = [f"c{i}" for i in range(len(cols))]
        return (f"SELECT {', '.join(f'{c} AS {n}' for c, n in zip(cols, names))} FROM {frm}"
                + (f" WHERE {' AND '.join(where)}" if where else "")), names
    if isinstance(top, TopK):
        frm, cols, where = _from_clause(top.child)
        names = [f"c{i}" for i in range(len(cols))]
        inner = ", ".join(f"{c} AS {n}" for c, n in zip(cols, names))
        part = ", ".join(cols[i] for i in top.pcols)
        order = ", ".join([f"{cols[i]} ASC NULLS LAST" for i in top.ocols] + [f"{c} ASC NULLS LAST" for c in cols])
        sql = (f"SELECT {', '.join(names)} FROM (SELECT {inner}, ROW_NUMBER() OVER (PARTITION BY {part} ORDER BY {order}) AS rn "
               f"FROM {frm}" + (f" WHERE {' AND '.join(where)}" if where else "") + f") AS qt WHERE rn <= {top.k}")
        return sql, names
    raise UnsupportedSemantics(type(top).__name__)


class CanonicalizationError(Exception):
    pass


def coerce(v, typ: str):
    if v is None:
        return None
    if isinstance(v, bool) or isinstance(v, float):
        raise CanonicalizationError(f"inexact value {v!r}")
    if typ == "int":
        if isinstance(v, int):
            return v
        if isinstance(v, Decimal) and v == v.to_integral_value():
            return int(v)
        if isinstance(v, str) and v.lstrip("-").isdigit():
            return int(v)
        raise CanonicalizationError(f"non-integral value {v!r} for int column")
    if typ == "dec":
        if isinstance(v, (int, Decimal)):
            return Decimal(v)
        if isinstance(v, str):
            return Decimal(v)
        raise CanonicalizationError(f"bad decimal {v!r}")
    if not isinstance(v, str):
        raise CanonicalizationError(f"bad text {v!r}")
    return v


def postprocess(view: View, schema, names: List[str], rows) -> ZSet:
    """Canonical view rows from target rows. AVG equality rule: |avg - SUM/COUNT| <= half unit of the target's scale."""
    types = col_types(view.top, schema)
    z = ZSet()
    for r in rows:
        rec = dict(zip(names, r)); out = []
        for j, t in enumerate(types):
            n = f"c{j}"
            if f"{n}_s" in rec:
                s, cnt, avg = rec[f"{n}_s"], rec[f"{n}_n"], rec[n]
                if s is None or not cnt:
                    if avg is not None:
                        raise CanonicalizationError("AVG non-NULL over empty input")
                    out.append(None); continue
                exact = Decimal(s) / Decimal(int(cnt))
                if avg is None:
                    out.append("AVG_MISMATCH:NULL"); continue
                if isinstance(avg, float):          # binary AVG (e.g. DOUBLE): relative tolerance 1e-9
                    a = Decimal(repr(avg)); tol = Decimal("1e-9") * max(Decimal(1), abs(exact))
                else:                               # decimal AVG: half a unit in the target's reported scale
                    a = avg if isinstance(avg, Decimal) else Decimal(str(avg))
                    tol = Decimal(1).scaleb(-max(-a.as_tuple().exponent, 0)) / 2
                out.append(exact.quantize(AVG_Q, rounding=ROUND_HALF_EVEN) if abs(a - exact) <= tol else f"AVG_MISMATCH:{a}")
            else:
                out.append(coerce(rec[n], t))
        z.add_row(tuple(out), 1)
    return z


def ddl(schema, dialect: str) -> List[str]:
    tmap = {"int": "BIGINT", "dec": "DECIMAL(18,4)", "text": "VARCHAR"}
    out = []
    for name in schema.order:
        tb = schema.tables[name]
        cols = [f"c{i} {tmap[t]}{'' if nl else ' NOT NULL'}" for i, (_, t, nl) in enumerate(tb.cols)]
        if tb.pk is not None and dialect in ("postgres", "risingwave", "feldera"):
            cols.append("PRIMARY KEY (" + ", ".join(f"c{i}" for i in tb.pk) + ")")
        out.append(f"CREATE TABLE {name} (" + ", ".join(cols) + ")")
    return out
