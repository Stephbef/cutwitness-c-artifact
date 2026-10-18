import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from cutwitness.adapters import mocks as M
from cutwitness.adapters.feldera import FelderaAdapter
from cutwitness.adapters.pgwire import PgIvmAdapter, RisingWaveAdapter
from cutwitness.simtargets import applicable_views
from cutwitness.w3 import gen_schema, gen_views

T = {"sql_s": 10, "ready_s": 2, "stop_s": 5, "lifecycle_s": 30, "compile_s": 10, "barrier_s": 2}


def mock_sessions(seed=1, pg_faults=None, rw_faults=None, feldera_faults=None, docker_fail=None):
    M.reset_mocks(); rng = random.Random(seed); s = gen_schema(rng); vs = gen_views(rng, s)
    pv = applicable_views(vs, {"ops": PgIvmAdapter.OPS})
    pg = M.mock_server("pg", "postgres", "170010"); pg.faults.update(pg_faults or {})
    rw = M.mock_server("rw", "risingwave", "3.1.0"); rw.faults.update(rw_faults or {})
    dpg = M.MockDocker({"cw-pgivm": pg}, fail_on=docker_fail); drw = M.MockDocker({"cw-risingwave": rw}, fail_on=docker_fail)
    fm = M.MockFeldera(faults=feldera_faults or {})

    def mk_pg(name):
        pg.db(name); a = PgIvmAdapter(s, pv, M.MockPgSql(f"mock://pg/{name}", 10), dpg, {"dsn_template": "mock://pg/{db}", "container_name": "cw-pgivm"}, T, name)
        a.create_schema(); a.create_views(); return a

    def mk_rw(name):
        rw.db(name); a = RisingWaveAdapter(s, vs, M.MockPgSql(f"mock://rw/{name}", 10), drw,
                                           {"dsn_template": "mock://rw/{db}", "rescale_parallelism": 2, "container_name": "cw-risingwave"}, T, name)
        a.create_schema(); a.create_views(); return a

    def mk_fe(name):
        a = FelderaAdapter(s, vs, fm, M.MockDocker(), {"workers": 2}, T, name); a.create_schema(); a.create_views(); return a
    return {"schema": s, "views": vs, "pg_views": pv, "pg": (mk_pg, pg, dpg), "rw": (mk_rw, rw, drw), "fe": (mk_fe, fm)}


@pytest.fixture
def mocks():
    return mock_sessions
