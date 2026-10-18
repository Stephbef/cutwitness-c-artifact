"""pg_ivm (PostgreSQL 17) and RisingWave adapters over the PostgreSQL wire protocol."""
from __future__ import annotations
import re
from typing import Dict, List
from ..model import Txn, ZSet
from ..targetsql import CanonicalizationError, ddl, postprocess, target_sql
from .base import SUPPORTED, UNSUPPORTED, Adapter, AdapterFailure, CapabilityUnsupported, wait_until


def _vals(r):
    return list(r)


class PgWireAdapter(Adapter):
    dialect = "postgres"
    container = None

    def __init__(self, schema, views, sql, docker, env: dict, timeouts: dict, session: str):
        self.schema, self.views, self.sql, self.docker, self.env, self.t = schema, views, sql, docker, env, timeouts
        self.session = session
        self.container = env.get("container_name", self.container)
        self.names: Dict[str, List[str]] = {}
        self.view_sql: Dict[str, str] = {}

    # ---- setup
    def create_schema(self):
        for stmt in ddl(self.schema, self.dialect):
            self.sql.execute(stmt)

    def create_views(self):
        for v in self.views:
            q, names = target_sql(v, self.schema, self.dialect)
            self.names[v.name] = names; self.view_sql[v.name] = q
            self._create_view(v.name, q)

    # ---- data
    def apply_transaction(self, t: Txn):
        """Deletes first (children before parents), then inserts (parents before children): primary-key updates and
        foreign keys stay legal statement by statement, and engines with upsert-on-conflict cannot overwrite."""
        order = [n for n in self.schema.order if n in t.delta]
        dels, ins = [], []
        for table in reversed(order):
            for r, m in t.delta[table].items_sorted():
                if m < 0:
                    cond = " AND ".join(f"c{i} IS NULL" if v is None else f"c{i} = %s" for i, v in enumerate(r))
                    params = [v for v in r if v is not None]
                    dels += [(self._delete_one(table, cond), params)] * (-m)
        for table in order:
            for r, m in t.delta[table].items_sorted():
                if m > 0:
                    ins += [("INSERT INTO {} VALUES ({})".format(table, ", ".join(["%s"] * len(r))), list(r))] * m
        self._begin()
        for stmt, p in dels + ins:
            self.sql.execute(stmt, p)
        self._commit()

    def read_views(self) -> Dict[str, ZSet]:
        out = {}
        for v in self.views:
            names = self.names[v.name]
            rows = self.sql.execute(f"SELECT {', '.join(names)} FROM {v.name}")
            try:
                out[v.name] = postprocess(v, self.schema, names, rows)
            except CanonicalizationError as e:
                raise AdapterFailure("CANONICALIZATION", str(e))
        return out

    def clean_rebuild(self, x) -> Dict[str, ZSet]:
        fresh = self.fresh_session(self.session + "_clean")
        try:
            fresh.create_schema()
            fresh.apply_transaction(Txn({t: z for t, z in x.items()}))
            fresh.create_views(); fresh.flush()
            return fresh.read_views()
        finally:
            fresh.destroy()

    def _wait_ready(self):
        def ok():
            self.sql.close()
            self.sql.execute("SELECT 1"); return True
        wait_until(ok, self.t["ready_s"], 1.0, "ready after lifecycle")

    def restart(self):
        self.sql.close(); self.docker.run(["restart", "-t", str(int(self.t["stop_s"])), self.container], self.t["lifecycle_s"])
        self._wait_ready()

    def kill_recover(self):
        self.sql.close(); self.docker.run(["kill", "--signal=KILL", self.container], self.t["lifecycle_s"])
        self.docker.run(["start", self.container], self.t["lifecycle_s"]); self._wait_ready()


class PgIvmAdapter(PgWireAdapter):
    target = "pg_ivm"
    dialect = "postgres"
    container = "cw-pgivm"
    OPS = {"group": SUPPORTED, "distinct": SUPPORTED, "join": SUPPORTED, "leftjoin": SUPPORTED, "topk": UNSUPPORTED}
    LIFECYCLE = {"RESTART": SUPPORTED, "KILL_RECOVER": SUPPORTED, "CHECKPOINT": SUPPORTED, "RESTORE_LATEST": UNSUPPORTED,
                 "RESCALE": UNSUPPORTED, "UPGRADE": UNSUPPORTED, "REPLACE_VIEW_IDENTICAL": SUPPORTED, "COMPACT": SUPPORTED}

    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.fn = None

    def probe(self) -> dict:
        ver = self.sql.execute("SELECT current_setting('server_version_num')")[0][0]
        ext = self.sql.execute("SELECT extversion FROM pg_extension WHERE extname = 'pg_ivm'")
        ns = self.sql.execute("SELECT n.nspname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE p.proname = 'create_immv'")
        if not ns:
            raise AdapterFailure("VERSION_MISMATCH", "pg_ivm create_immv not found")
        self.fn = ns[0][0]
        return {"server_version_num": str(ver), "pg_ivm": ext[0][0] if ext else None, "fn_schema": self.fn}

    def fresh_session(self, name):
        return PgIvmAdapter(self.schema, self.views, self.sql.__class__(self.env["dsn_template"].format(db=name), self.t["sql_s"]),
                            self.docker, self.env, self.t, name)

    def _create_view(self, name, q):
        if self.fn is None:
            self.probe()
        self.sql.execute(f"SELECT {self.fn}.create_immv(%s, %s)", [name, q])

    def _delete_one(self, table, cond):
        return f"DELETE FROM {table} WHERE ctid = (SELECT ctid FROM {table} WHERE {cond} LIMIT 1)"

    def _begin(self): self.sql.execute("BEGIN")
    def _commit(self): self.sql.execute("COMMIT")
    def flush(self): return True  # immediate IVM: maintenance is inside the committing transaction

    def checkpoint(self): self.sql.execute("CHECKPOINT")
    def compact(self):
        for name in self.schema.order:
            self.sql.execute(f"VACUUM FULL {name}")
        for v in self.views:
            self.sql.execute(f"VACUUM FULL {v.name}")

    def replace_view_identical(self):
        for v in self.views:
            self.sql.execute(f"DROP TABLE {v.name}"); self._create_view(v.name, self.view_sql[v.name])

    def destroy(self):
        self.sql.close()
        admin = self.sql.__class__(self.env["dsn_template"].format(db="postgres"), self.t["sql_s"])
        try:
            admin.execute(f'DROP DATABASE IF EXISTS "{self.session}" WITH (FORCE)')
        finally:
            admin.close()

    @classmethod
    def create_session_db(cls, admin, name, ext_version):
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'); admin.execute(f'CREATE DATABASE "{name}"')
        return f"CREATE EXTENSION pg_ivm VERSION '{ext_version}'"


class RisingWaveAdapter(PgWireAdapter):
    target = "risingwave"
    dialect = "risingwave"
    container = "cw-risingwave"
    OPS = {"group": SUPPORTED, "distinct": SUPPORTED, "join": SUPPORTED, "leftjoin": SUPPORTED, "topk": SUPPORTED}
    LIFECYCLE = {"RESTART": SUPPORTED, "KILL_RECOVER": SUPPORTED, "CHECKPOINT": UNSUPPORTED, "RESTORE_LATEST": UNSUPPORTED,
                 "RESCALE": SUPPORTED, "UPGRADE": UNSUPPORTED, "REPLACE_VIEW_IDENTICAL": SUPPORTED, "COMPACT": UNSUPPORTED}

    def probe(self) -> dict:
        v = self.sql.execute("SELECT version()")[0][0]
        m = re.search(r"RisingWave-(\d+\.\d+\.\d+)", v)
        if not m:
            raise AdapterFailure("MALFORMED_RESPONSE", f"unexpected version string {v!r}")
        return {"version": m.group(1)}

    def fresh_session(self, name):
        return RisingWaveAdapter(self.schema, self.views, self.sql.__class__(self.env["dsn_template"].format(db=name), self.t["sql_s"]),
                                 self.docker, self.env, self.t, name)

    def _create_view(self, name, q):
        self.sql.execute(f"CREATE MATERIALIZED VIEW {name} AS {q}")

    def _delete_one(self, table, cond):
        tb = self.schema.tables[table]
        if tb.pk is None:
            raise CapabilityUnsupported("DELETE_ONE_COPY", "RisingWave tables without a primary key cannot delete a single duplicate")
        return f"DELETE FROM {table} WHERE {cond}"

    def _begin(self): self.sql.execute("SET RW_IMPLICIT_FLUSH = false")
    def _commit(self): self.flush()

    def flush(self):
        self.sql.execute("FLUSH"); return True

    def rescale(self):
        n = self.env["rescale_parallelism"]
        for v in self.views:
            self.sql.execute(f"ALTER MATERIALIZED VIEW {v.name} SET PARALLELISM = {int(n)}")
        self.flush()

    def replace_view_identical(self):
        for v in self.views:
            self.sql.execute(f"DROP MATERIALIZED VIEW {v.name}"); self._create_view(v.name, self.view_sql[v.name])
        self.flush()

    def destroy(self):
        self.sql.close()
        admin = self.sql.__class__(self.env["dsn_template"].format(db="dev"), self.t["sql_s"])
        try:
            admin.execute(f"DROP DATABASE IF EXISTS {self.session}")
        finally:
            admin.close()
