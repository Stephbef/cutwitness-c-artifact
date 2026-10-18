"""Transports: SQL (psycopg), HTTP (urllib), container commands (docker CLI) with hard timeouts."""
from __future__ import annotations
import json, os, signal, subprocess, urllib.error, urllib.parse, urllib.request
from typing import Dict, List, Optional
from .base import AdapterFailure


class PgSql:
    def __init__(self, dsn: str, timeout_s: float):
        self.dsn, self.timeout_s, self.conn = dsn, timeout_s, None

    def connect(self):
        import psycopg
        try:
            self.conn = psycopg.connect(self.dsn, autocommit=True, connect_timeout=int(self.timeout_s))
            self.conn.execute(f"SET statement_timeout = {int(self.timeout_s * 1000)}") if "4566" not in self.dsn else None
        except Exception as e:
            raise AdapterFailure("CONNECTION", f"{type(e).__name__}: {e}")

    def execute(self, sql: str, params=None):
        if self.conn is None:
            self.connect()
        try:
            cur = self.conn.execute(sql, params) if params is not None else self.conn.execute(sql)
            return cur.fetchall() if cur.description else []
        except Exception as e:
            name = type(e).__name__
            kind = "TIMEOUT" if "Cancel" in name or "timeout" in str(e).lower() else ("CONNECTION" if "Operational" in name else "TARGET_ERROR")
            if kind == "CONNECTION":
                self.conn = None
            raise AdapterFailure(kind, f"{name}: {e}")

    def executemany(self, sql: str, rows):
        if self.conn is None:
            self.connect()
        try:
            with self.conn.cursor() as cur:
                cur.executemany(sql, rows)
        except Exception as e:
            raise AdapterFailure("TARGET_ERROR", f"{type(e).__name__}: {e}")

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            finally:
                self.conn = None


class Http:
    def __init__(self, base: str, timeout_s: float, headers: Optional[Dict[str, str]] = None):
        self.base, self.timeout_s, self.headers = base.rstrip("/"), timeout_s, headers or {}

    def request(self, method: str, path: str, body=None, query: Optional[dict] = None, raw: Optional[bytes] = None):
        url = self.base + path + (("?" + urllib.parse.urlencode(query)) if query else "")
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **self.headers})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise AdapterFailure("TIMEOUT" if "timed out" in str(e) else "CONNECTION", str(e))


class Docker:
    """docker CLI wrapper; every command has a hard timeout and runs in its own process group."""

    def __init__(self, binary: str = "docker"):
        self.binary = binary
        self.log: List[List[str]] = []

    def run(self, args: List[str], timeout_s: float) -> str:
        cmd = [self.binary] + args
        self.log.append(cmd)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            out, err = p.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL); p.communicate()
            raise AdapterFailure("TIMEOUT", " ".join(cmd))
        if p.returncode != 0:
            raise AdapterFailure("TARGET_ERROR", f"{' '.join(cmd)} -> {p.returncode}: {err.decode()[-400:]}")
        return out.decode()
