"""Protocol-level mocks (engineering verification only): DuckDB-backed pgwire SQL, Feldera REST, docker CLI."""
from __future__ import annotations
import json, re
from typing import Dict, List, Optional
from .base import AdapterFailure

_SERVERS: Dict[str, "MockPgServer"] = {}


class MockPgServer:
    """One mock server: databases = DuckDB connections; persists across mock restarts unless a fault drops state."""

    def __init__(self, flavor: str, version: str, ext_version: str = "1.15"):
        import duckdb
        self.duckdb = duckdb
        self.flavor, self.version, self.ext_version = flavor, version, ext_version
        self.dbs: Dict[str, object] = {}
        self.up = True
        self.faults: Dict[str, object] = {}
        self.log: List[str] = []
        self.stmt_count = 0

    def db(self, name):
        if name not in self.dbs:
            self.dbs[name] = self.duckdb.connect(":memory:")
        return self.dbs[name]


def mock_server(key: str, flavor: str = "postgres", version: str = "170006") -> MockPgServer:
    if key not in _SERVERS:
        _SERVERS[key] = MockPgServer(flavor, version)
    return _SERVERS[key]


def reset_mocks():
    _SERVERS.clear()


class MockPgSql:
    """Same interface as transport.PgSql; dsn form mock://<server>/<db>."""

    def __init__(self, dsn: str, timeout_s: float):
        m = re.match(r"mock://([^/]+)/(.+)", dsn)
        self.server = _SERVERS[m.group(1)]; self.dbname = m.group(2); self.timeout_s = timeout_s; self.open = False

    def connect(self):
        if self.server.faults.get("never_ready"):
            raise AdapterFailure("CONNECTION", "mock server never ready")
        if not self.server.up:
            raise AdapterFailure("CONNECTION", "mock server down")
        self.open = True

    def close(self):
        self.open = False

    def executemany(self, sql, rows):
        for r in rows:
            self.execute(sql, r)

    def execute(self, sql: str, params=None):
        sv = self.server
        if not self.open or not sv.up:
            self.open = False
            self.connect()
        sv.stmt_count += 1; sv.log.append(sql)
        f = sv.faults
        if f.get("timeout_at") == sv.stmt_count:
            raise AdapterFailure("TIMEOUT", "mock statement timeout")
        if f.get("drop_at") == sv.stmt_count:
            self.open = False; raise AdapterFailure("CONNECTION", "mock connection dropped")
        s = sql.strip()
        u = s.upper()
        con = sv.db(self.dbname)
        if u.startswith("SET ") or u in ("BEGIN", "COMMIT", "FLUSH", "CHECKPOINT") or u.startswith("VACUUM") or "SET PARALLELISM" in u:
            if u in ("BEGIN", "COMMIT"):
                con.execute(u)
            return []
        if u == "SELECT 1":
            return [(1,)]
        if "SERVER_VERSION_NUM" in u:
            return [(f.get("version_override", sv.version),)]
        if u.startswith("SELECT VERSION()"):
            return [(f.get("version_string", f"PostgreSQL 13.14.0-RisingWave-{sv.version} (mock)"),)]
        if "FROM PG_EXTENSION" in u:
            return [(sv.ext_version,)]
        if "FROM PG_PROC" in u:
            return [] if f.get("no_pg_ivm") else [("pgivm",)]
        if u.startswith("ALTER EXTENSION PG_IVM UPDATE TO"):
            sv.ext_version = re.search(r"'([^']+)'", s).group(1); return []
        if u.startswith("DROP DATABASE"):
            name = re.search(r'"?([A-Za-z0-9_]+)"?\s*(WITH|$)', s.split("EXISTS", 1)[-1].strip()).group(1)
            sv.dbs.pop(name, None); return []
        if u.startswith("CREATE DATABASE"):
            sv.db(re.search(r'"?([A-Za-z0-9_]+)"?', s[len("CREATE DATABASE"):].strip()).group(1)); return []
        if u.startswith("CREATE EXTENSION"):
            return []
        m = re.match(r"SELECT (\w+)\.create_immv\(%s, %s\)", s)
        if m:
            name, q = params
            con.execute(f"CREATE VIEW {name} AS {q}"); return []
        m = re.match(r"CREATE MATERIALIZED VIEW (\w+) AS (.*)", s, re.S)
        if m:
            con.execute(f"CREATE VIEW {m.group(1)} AS {m.group(2)}"); return []
        m = re.match(r"DROP (?:MATERIALIZED VIEW|TABLE) (\w+)", s)
        if m and m.group(1).startswith("v"):
            con.execute(f"DROP VIEW {m.group(1)}"); return []
        if u.startswith("CREATE TABLE"):
            # DuckDB rejects delete-then-reinsert of one key inside a transaction (documented index limitation) where
            # PostgreSQL/RisingWave accept it; the mock drops the PRIMARY KEY clause. Statement ordering is pinned by
            # the golden protocol-log tests instead.
            s = re.sub(r",\s*PRIMARY KEY \([^)]*\)", "", s)
        s2 = s.replace("ctid", "rowid").replace("%s", "?")
        if f.get("corrupt_reads") and u.startswith("SELECT") and " FROM V" in u:
            rows = con.execute(s2, params).fetchall() if params else con.execute(s2).fetchall()
            return rows[:-1]
        try:
            cur = con.execute(s2, params) if params else con.execute(s2)
        except AdapterFailure:
            raise
        except Exception as e:  # engine errors surface exactly like transport.PgSql: classified TARGET_ERROR
            raise AdapterFailure("TARGET_ERROR", f"{type(e).__name__}: {e}")
        try:
            return cur.fetchall()
        except Exception:
            return []


class MockDocker:
    def __init__(self, servers: Dict[str, MockPgServer] = None, fail_on: Optional[str] = None, lose_state_on: Optional[str] = None):
        self.servers = servers or {}; self.log: List[List[str]] = []; self.fail_on = fail_on; self.lose_state_on = lose_state_on

    def run(self, args: List[str], timeout_s: float) -> str:
        self.log.append(["docker"] + args)
        if self.fail_on and self.fail_on == args[0]:
            raise AdapterFailure("TIMEOUT", "mock docker timeout")
        if args and args[0] == "run" and "--name" in args:
            name = args[args.index("--name") + 1]
            sv = self.servers.get(name)
            if sv is not None:
                sv.up = True
                img = next((a for a in args if ":v" in a), None)
                if img:
                    sv.version = img.rsplit(":v", 1)[1]
                if "--fresh-data" in args or any(a.endswith(":/data") and "fresh" in a for a in args):
                    sv.dbs.clear()
            return ""
        name = args[-1] if args else ""
        sv = self.servers.get(name)
        if sv is not None and args[0] in ("restart", "start", "kill", "stop"):
            if args[0] in ("kill", "stop"):
                sv.up = False
            else:
                sv.up = True
            if self.lose_state_on == args[0]:
                for con in sv.dbs.values():
                    for (t,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_type='BASE TABLE'").fetchall():
                        con.execute(f"DELETE FROM {t}")
        return ""


class MockFeldera:
    """In-process Feldera pipeline-manager REST mock with fault injection."""

    def __init__(self, version: str = "0.366.0", compile_polls: int = 2, faults: Optional[dict] = None):
        import duckdb
        self.duckdb = duckdb; self.version = version; self.compile_polls = compile_polls
        self.p: Dict[str, dict] = {}; self.log: List[list] = []; self.faults = faults or {}

    def request(self, method, path, body=None, query=None, raw=None):
        self.log.append([method, path, query or {}, (raw or b"")[:120].decode(errors="replace") if raw else body and {"name": body.get("name")}])
        if self.faults.get("http500_on") and self.faults["http500_on"] in path:
            return 500, b"internal"
        if path == "/v0/config":
            return 200, (b"not json" if self.faults.get("malformed_config") else json.dumps({"version": self.version}).encode())
        m = re.match(r"/v0/pipelines/([\w]+)(/.*)?$", path)
        name, sub = m.group(1), m.group(2) or ""
        p = self.p.get(name)
        if method == "PUT" and sub == "":
            self.p[name] = {"program": body["program_code"], "polls": 0, "status": "Stopped", "db": None, "ckpt": None,
                            "inputs": 0, "storage": body["runtime_config"].get("storage")}
            return 201, b"{}"
        if p is None:
            return 404, b"no pipeline"
        if method == "GET" and sub == "":
            p["polls"] += 1
            ps = ("CompilingRust" if p["polls"] <= self.compile_polls else "Success")
            if self.faults.get("compile_error"):
                ps = {"SqlError": "mock"}
            return 200, json.dumps({"program_status": ps, "deployment_status": p["status"]}).encode()
        if method == "POST" and sub == "/start":
            if p["db"] is None:
                p["db"] = self.duckdb.connect(":memory:")
                for stmt in [x.strip() for x in p["program"].split(";") if x.strip()]:
                    p["db"].execute(stmt.replace("CREATE MATERIALIZED VIEW", "CREATE VIEW").replace("VARCHAR NOT NULL", "VARCHAR NOT NULL"))
            p["status"] = "Running"; return 202, b"{}"
        if method == "POST" and sub == "/stop":
            force = (query or {}).get("force") == "true"
            if force and p["storage"] and p["ckpt"] is not None:
                p["db"] = self._restore(p)
            elif force and not p["storage"]:
                p["db"] = None
            p["status"] = "Stopped"; return 202, b"{}"
        if method == "POST" and sub == "/clear":
            p["db"] = None; p["ckpt"] = None; return 202, b"{}"
        if method == "POST" and sub == "/checkpoint":
            p["ckpt"] = self._dump(p); return 200, b"{}"
        if method == "DELETE" and sub == "":
            self.p.pop(name, None); return 200, b"{}"
        if method == "GET" and sub == "/stats":
            if self.faults.get("stats_missing"):
                return 200, b'{"global_metrics": {}}'
            return 200, json.dumps({"global_metrics": {"total_input_records": p["inputs"], "total_processed_records": p["inputs"],
                                                       "buffered_input_records": 0}}).encode()
        m2 = re.match(r"/ingress/(\w+)", sub)
        if method == "POST" and m2:
            t = m2.group(1)
            for ln in raw.decode().splitlines():
                rec = json.loads(ln); op = "insert" if "insert" in rec else "delete"; vals = rec[op]
                cols = sorted(vals, key=lambda c: int(c[1:]))
                if op == "insert":
                    p["db"].execute(f"INSERT INTO {t} VALUES ({', '.join('?' for _ in cols)})", [vals[c] for c in cols])
                else:
                    cond = " AND ".join(f"{c} IS NULL" if vals[c] is None else f"{c} = ?" for c in cols)
                    p["db"].execute(f"DELETE FROM {t} WHERE rowid = (SELECT rowid FROM {t} WHERE {cond} LIMIT 1)", [vals[c] for c in cols if vals[c] is not None])
                p["inputs"] += 1
            return 200, b"{}"
        if method == "GET" and sub == "/query":
            cur = p["db"].execute(query["sql"]); names = [d[0] for d in cur.description]
            lines = [json.dumps({n: (format(v, "f") if hasattr(v, "as_tuple") else v) for n, v in zip(names, r)}) for r in cur.fetchall()]
            return 200, "\n".join(lines).encode()
        return 404, b"unknown endpoint"

    def _dump(self, p):
        tables = [t for (t,) in p["db"].execute("SELECT table_name FROM information_schema.tables WHERE table_type='BASE TABLE'").fetchall()]
        return {t: p["db"].execute(f"SELECT * FROM {t}").fetchall() for t in tables}

    def _restore(self, p):
        db = self.duckdb.connect(":memory:")
        for stmt in [x.strip() for x in p["program"].split(";") if x.strip()]:
            db.execute(stmt.replace("CREATE MATERIALIZED VIEW", "CREATE VIEW"))
        for t, rows in p["ckpt"].items():
            for r in rows:
                db.execute(f"INSERT INTO {t} VALUES ({', '.join('?' for _ in r)})", list(r))
        return db
