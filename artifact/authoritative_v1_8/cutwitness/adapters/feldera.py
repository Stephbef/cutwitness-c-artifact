"""Feldera adapter over the pipeline-manager REST API (one compiled program per trial, cleared per history)."""
from __future__ import annotations
import json
from decimal import Decimal
from typing import Dict
from ..model import Txn, ZSet
from ..targetsql import CanonicalizationError, ddl, postprocess, target_sql
from .base import SUPPORTED, UNSUPPORTED, Adapter, AdapterFailure, CapabilityUnsupported, wait_until


def _jsonable(v):
    if isinstance(v, Decimal):
        return format(v, "f")
    return v


class FelderaAdapter(Adapter):
    target = "feldera"
    OPS = {"group": SUPPORTED, "distinct": SUPPORTED, "join": SUPPORTED, "leftjoin": SUPPORTED, "topk": SUPPORTED}
    LIFECYCLE = {"RESTART": SUPPORTED, "KILL_RECOVER": SUPPORTED, "CHECKPOINT": SUPPORTED, "RESTORE_LATEST": SUPPORTED,
                 "RESCALE": UNSUPPORTED, "UPGRADE": UNSUPPORTED, "REPLACE_VIEW_IDENTICAL": UNSUPPORTED, "COMPACT": UNSUPPORTED}

    def __init__(self, schema, views, http, docker, env: dict, timeouts: dict, pipeline: str):
        self.schema, self.views, self.http, self.docker, self.env, self.t = schema, views, http, docker, env, timeouts
        self.p = pipeline; self.names: Dict[str, list] = {}

    def _call(self, method, path, body=None, query=None, raw=None, ok=(200, 201, 202)):
        st, data = self.http.request(method, path, body, query, raw)
        if st not in ok:
            raise AdapterFailure("TARGET_ERROR" if st < 500 else "CONNECTION", f"{method} {path} -> {st}: {data[:300]!r}")
        return data

    def _json(self, data):
        try:
            return json.loads(data)
        except (ValueError, TypeError):
            raise AdapterFailure("MALFORMED_RESPONSE", repr(data[:200]))

    def probe(self) -> dict:
        cfg = self._json(self._call("GET", "/v0/config"))
        ver = cfg.get("version") if isinstance(cfg, dict) else None
        if not isinstance(ver, str):
            raise AdapterFailure("MALFORMED_RESPONSE", "no version in /v0/config")
        return {"version": ver}

    def program(self) -> str:
        stmts = ddl(self.schema, "feldera")
        for v in self.views:
            q, names = target_sql(v, self.schema, "feldera"); self.names[v.name] = names
            stmts.append(f"CREATE MATERIALIZED VIEW {v.name} AS {q}")
        return ";\n".join(stmts) + ";"

    def _status(self):
        return self._json(self._call("GET", f"/v0/pipelines/{self.p}"))

    def create_schema(self):
        body = {"name": self.p, "description": "cutwitness-c", "program_code": self.program(),
                "runtime_config": {"workers": int(self.env["workers"]), "storage": self.env.get("storage", True),
                                   "fault_tolerance": self.env.get("fault_tolerance", {"model": "exactly_once"})},
                "program_config": {}}
        self._call("PUT", f"/v0/pipelines/{self.p}", body)
        wait_until(lambda: self._compiled(), self.t["compile_s"], 2.0, "program compiled")

    def _compiled(self):
        s = self._status(); ps = s.get("program_status")
        if isinstance(ps, dict) or (isinstance(ps, str) and "Error" in ps):
            raise AdapterFailure("TARGET_ERROR", f"compilation failed: {str(ps)[:300]}")
        return ps == "Success"

    def create_views(self):
        self._start()

    def _start(self):
        self._call("POST", f"/v0/pipelines/{self.p}/start")
        wait_until(lambda: self._status().get("deployment_status") == "Running", self.t["ready_s"], 1.0, "ready running")

    def _stop(self, force: bool):
        self._call("POST", f"/v0/pipelines/{self.p}/stop", query={"force": "true" if force else "false"})
        wait_until(lambda: self._status().get("deployment_status") == "Stopped", self.t["lifecycle_s"], 1.0, "stopped")

    def apply_transaction(self, t: Txn):
        order = [n for n in self.schema.order if n in t.delta]
        for table in order:                      # per table: deletes before inserts (primary-key upsert safety)
            lines = []
            items = t.delta[table].items_sorted()
            for r, m in [x for x in items if x[1] < 0] + [x for x in items if x[1] > 0]:
                rec = {f"c{i}": _jsonable(v) for i, v in enumerate(r)}
                lines += [json.dumps({"insert" if m > 0 else "delete": rec})] * abs(m)
            self._call("POST", f"/v0/pipelines/{self.p}/ingress/{table}",
                       query={"format": "json", "update_format": "insert_delete", "array": "false"}, raw="\n".join(lines).encode())
        self.flush()

    def flush(self):
        def done():
            st = self._json(self._call("GET", f"/v0/pipelines/{self.p}/stats"))
            g = st.get("global_metrics", {})
            if "total_input_records" not in g or "total_processed_records" not in g:
                raise AdapterFailure("MALFORMED_RESPONSE", "stats without record counters")
            return g["total_processed_records"] >= g["total_input_records"] and g.get("buffered_input_records", 0) == 0
        wait_until(done, self.t["barrier_s"], 0.2, "barrier")
        return True

    def read_views(self) -> Dict[str, ZSet]:
        out = {}
        for v in self.views:
            names = self.names[v.name]
            raw = self._call("GET", f"/v0/pipelines/{self.p}/query", query={"sql": f"SELECT {', '.join(names)} FROM {v.name}", "format": "json"})
            rows = []
            for ln in raw.decode().splitlines():
                if ln.strip():
                    rec = self._json(ln)
                    rows.append([_parse(rec.get(n)) for n in names])
            try:
                out[v.name] = postprocess(v, self.schema, names, rows)
            except CanonicalizationError as e:
                raise AdapterFailure("CANONICALIZATION", str(e))
        return out

    def restart(self):
        self._stop(force=False); self._start()

    def kill_recover(self):
        self._stop(force=True); self._start()

    def checkpoint(self):
        self._call("POST", f"/v0/pipelines/{self.p}/checkpoint")

    def restore_latest(self):
        self._stop(force=True); self._start()   # exactly-once fault tolerance resumes from the latest checkpoint

    def clean_rebuild(self, x) -> Dict[str, ZSet]:
        fresh = FelderaAdapter(self.schema, self.views, self.http, self.docker, self.env, self.t, self.p + "_clean")
        try:
            fresh.create_schema(); fresh.create_views()
            fresh.apply_transaction(Txn({t: z for t, z in x.items()}))
            return fresh.read_views()
        finally:
            fresh.destroy()

    def reset(self):
        self._stop(force=True); self._call("POST", f"/v0/pipelines/{self.p}/clear"); self._start()

    def destroy(self):
        try:
            self._stop(force=True)
        finally:
            self._call("DELETE", f"/v0/pipelines/{self.p}", ok=(200, 202, 404))


def _parse(v):
    """JSON floats stay binary so canonicalization applies the binary-AVG rule (and rejects floats elsewhere)."""
    if isinstance(v, str):
        try:
            if any(ch.isdigit() for ch in v) and v.replace(".", "", 1).lstrip("-").isdigit():
                return Decimal(v) if "." in v else int(v)
        except Exception:
            return v
    return v
