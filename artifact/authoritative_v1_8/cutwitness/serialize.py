"""Schema/view (de)serialization for witness packages and replay."""
from __future__ import annotations
from .model import Schema, Table
from .refmodel import View, plan_from_json


def schema_from_json(j) -> Schema:
    return Schema([Table(t["name"], [tuple(c) for c in t["cols"]], t["pk"], [(c, p, pc) for c, p, pc in t["fks"]]) for t in j["tables"]])


def views_from_json(schema, js):
    ar = {n: schema.tables[n].arity for n in schema.order}
    return [View(v["name"], plan_from_json(v["plan"], v["name"], ar)) for v in js]
