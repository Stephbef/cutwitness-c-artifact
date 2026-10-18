"""Real-target orchestration: container definitions, isolation, image-digest pinning, session factories."""
from __future__ import annotations
from typing import Callable, Dict
from .adapters.base import AdapterFailure
from .adapters.feldera import FelderaAdapter
from .adapters.pgwire import PgIvmAdapter, RisingWaveAdapter
from .isolation import docker_run_args

ADAPTERS = {"pg_ivm": PgIvmAdapter, "risingwave": RisingWaveAdapter, "feldera": FelderaAdapter}


def resolve_digests(docker, images: Dict[str, str], timeout_s: float) -> Dict[str, str]:
    """Pull every pinned tag once and record its immutable repo digest (or image ID for locally built images)."""
    out = {}
    for name, ref in sorted(images.items()):
        if ref.startswith("build:"):
            ctx = ref[len("build:"):]
            docker.run(["build", "-t", f"cutwitness/{name}:frozen", ctx], timeout_s)
            out[name] = docker.run(["image", "inspect", "--format", "{{.Id}}", f"cutwitness/{name}:frozen"], timeout_s).strip()
        else:
            docker.run(["pull", ref], timeout_s)
            out[name] = docker.run(["image", "inspect", "--format", "{{index .RepoDigests 0}}", ref], timeout_s).strip()
        if not out[name]:
            raise AdapterFailure("VERSION_MISMATCH", f"no digest for {ref}")
    return out


def container_args(target: str, tcfg: dict, run_id: str, cpuset: str, scratch: str, port: int, image_ref: str) -> list:
    return docker_run_args(tcfg["container"], image_ref, cpuset, tcfg["memory_gb"], scratch, {port: tcfg["container_port"]},
                           {"cutwitness.run": run_id, "cutwitness.target": target}, tcfg.get("command"), tcfg.get("env"))


def session_factory(target: str, tcfg: dict, schema, views, timeouts: dict, docker, transports: dict, port: int,
                    container_name: str = None) -> Callable:
    """Return make_session(name) -> adapter with created schema and views. `transports` supplies the SQL/HTTP classes
    (production: transport.PgSql / transport.Http; local verification: protocol mocks)."""
    cls = ADAPTERS[target]
    env = dict(tcfg["adapter_env"]); env["dsn_template"] = env.get("dsn_template", "").replace("{port}", str(port))
    if container_name:
        env["container_name"] = container_name
    if target == "feldera":
        http = transports["http"](f"http://127.0.0.1:{port}", timeouts["sql_s"])

        def make(name):
            a = cls(schema, views, http, docker, env, timeouts, name); a.create_schema(); a.create_views(); return a
        return make

    def make(name):
        admin = transports["sql"](env["dsn_template"].format(db=env["admin_db"]), timeouts["sql_s"])
        try:
            if target == "pg_ivm":
                ext = PgIvmAdapter.create_session_db(admin, name, env["pg_ivm_version"])
            else:
                admin.execute(f"DROP DATABASE IF EXISTS {name}"); admin.execute(f"CREATE DATABASE {name}"); ext = None
        finally:
            admin.close()
        sql = transports["sql"](env["dsn_template"].format(db=name), timeouts["sql_s"])
        if ext:
            sql.execute(ext)
        a = cls(schema, views, sql, docker, env, timeouts, name); a.create_schema(); a.create_views(); return a
    return make


def slot_port(cfg: dict, target: str, slot: int) -> int:
    return cfg["resources"]["port_base"] + 10 * slot + sorted(cfg["targets"]).index(target)


def image_ref(name: str, tcfg: dict, digests: Dict[str, str]) -> str:
    if tcfg["image"].startswith("build:"):
        return f"cutwitness/{name}:frozen"
    return digests[name]  # immutable repo@sha256 digest recorded at S2


def launch_slot(cfg: dict, run_id: str, slot: int, digests: Dict[str, str], docker, run_dir: str, cpuset: str) -> Dict[str, dict]:
    """Start every target container for one slot (isolated cpuset, memory, scratch, loopback port) and wait for readiness."""
    import os
    from .isolation import scratch_dir
    out = {}
    for name in sorted(cfg["targets"]):
        t = cfg["targets"][name]; port = slot_port(cfg, name, slot); cname = f"{t['container']}-s{slot}"
        docker.run(["rm", "-f", cname], cfg["timeouts"]["lifecycle_s"])
        scratch = scratch_dir(os.path.join(run_dir, "scratch"), f"{name}-s{slot}")
        args = docker_run_args(cname, image_ref(name, t, digests), cpuset, t["memory_gb"], scratch, {port: t["container_port"]},
                               {"cutwitness.run": run_id, "cutwitness.target": name, "cutwitness.slot": str(slot)}, t.get("command"), t.get("env"))
        docker.run(args, cfg["timeouts"]["lifecycle_s"])
        out[name] = {"container": cname, "port": port, "image": image_ref(name, t, digests)}
    return out


def probe_ready(cfg: dict, name: str, port: int, transports: dict) -> dict:
    """Readiness and exact version evidence; raises AdapterFailure(READINESS/VERSION_MISMATCH) and never assumes success."""
    from .adapters.base import wait_until
    t = cfg["targets"][name]; env = t["adapter_env"]; tm = cfg["timeouts"]; ev = {}
    if name == "feldera":
        http = transports["http"](f"http://127.0.0.1:{port}", tm["sql_s"])
        def ok():
            st, data = http.request("GET", "/v0/config")
            if st != 200:
                raise AdapterFailure("CONNECTION", f"status {st}")
            import json
            ev["version"] = json.loads(data).get("version"); return True
        wait_until(ok, tm["ready_s"], 2.0, "ready feldera")
    else:
        dsn = env["dsn_template"].replace("{port}", str(port)).format(db=env["admin_db"])
        def ok():
            sql = transports["sql"](dsn, tm["sql_s"])
            try:
                if name == "pg_ivm":
                    ev["server_version_num"] = str(sql.execute("SELECT current_setting('server_version_num')")[0][0])
                    av = sql.execute("SELECT default_version FROM pg_available_extensions WHERE name = 'pg_ivm'")
                    ev["pg_ivm"] = av[0][0] if av else None
                else:
                    import re
                    v = sql.execute("SELECT version()")[0][0]; m = re.search(r"RisingWave-(\d+\.\d+\.\d+)", v)
                    ev["version"] = m.group(1) if m else v
                return True
            finally:
                sql.close()
        wait_until(ok, tm["ready_s"], 2.0, "ready " + name)
    for k, want in t["version"].items():
        if ev.get(k) != want:
            raise AdapterFailure("VERSION_MISMATCH", f"{name} {k}={ev.get(k)!r}, frozen {want!r}")
    return ev
