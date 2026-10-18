"""Adapter hardening: golden protocol logs, readiness, malformed responses, resets, crashes, refusals, isolation."""
import json, os, socket, subprocess, sys, time
import pytest
from cutwitness.adapters.base import AdapterFailure, CapabilityUnsupported
from cutwitness.isolation import PortAllocator, ResourcePlan, disk_ok, docker_run_args, orphan_cleanup, run_group, scratch_dir
from cutwitness.oracles import execute

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def test_golden_protocol_logs_unchanged():
    from make_golden import capture
    gold = json.load(open(os.path.join(ROOT, "tests", "fixtures", "golden_protocol_logs.json")))
    now = json.loads(json.dumps(capture(), sort_keys=True))
    assert now == gold


def test_golden_log_deletes_precede_inserts_within_each_transaction():
    gold = json.load(open(os.path.join(ROOT, "tests", "fixtures", "golden_protocol_logs.json")))
    for key in ("pg_ivm_sql", "risingwave_sql"):
        block = []
        for stmt in gold[key] + ["COMMIT"]:
            if stmt in ("BEGIN", "COMMIT", "FLUSH") or stmt.startswith("SET RW_IMPLICIT_FLUSH"):
                kinds = [b.split()[0] for b in block if b.split()[0] in ("DELETE", "INSERT")]
                assert kinds == sorted(kinds, key=lambda k: 0 if k == "DELETE" else 1), (key, kinds)
                block = []
            else:
                block.append(stmt)


def test_readiness_timeout_is_classified(mocks):
    m = mocks(1); mk, pg, dpg = m["pg"]; a = mk("ready")
    dpg.fail_on = None; pg.faults["never_ready"] = True
    a.docker.run(["kill", "--signal=KILL", "cw-pgivm"], 5)            # target stays down
    t0 = time.time()
    with pytest.raises(AdapterFailure) as e:
        a._wait_ready()
    assert e.value.kind in ("READINESS", "TIMEOUT") and time.time() - t0 < 10


def test_malformed_responses(mocks):
    m = mocks(1, rw_faults={"version_string": "garbage"}, feldera_faults={"malformed_config": True})
    with pytest.raises(AdapterFailure) as e:
        m["rw"][0]("mal").probe()
    assert e.value.kind == "MALFORMED_RESPONSE"
    with pytest.raises(AdapterFailure) as e:
        m["fe"][0]("mal").probe()
    assert e.value.kind == "MALFORMED_RESPONSE"
    m2 = mocks(1, feldera_faults={"stats_missing": True})
    import random
    from cutwitness.w3 import gen_history
    sess = m2["fe"][0]("mal2")
    with pytest.raises(AdapterFailure) as e:
        sess.apply_transaction(gen_history(random.Random(1), m2["schema"], 1)[0])   # barrier reads /stats
    assert e.value.kind == "MALFORMED_RESPONSE"


def test_connection_reset_and_target_crash_become_infrastructure_errors(mocks):
    from cutwitness.model import Txn, ZSet
    m = mocks(1, pg_faults={"drop_at": 12}); mk, pg, dpg = m["pg"]
    import random
    from cutwitness.w3 import gen_history
    h = gen_history(random.Random(1), m["schema"], 4)
    at_cut, steps, err = execute(lambda: mk("reset"), h)
    assert at_cut is None and err is not None and "CONNECTION" in err
    m = mocks(2); mk, pg, dpg = m["pg"]; a = mk("crash")
    pg.up = False
    with pytest.raises(AdapterFailure) as e:
        a.sql.close(); a.read_views()
    assert e.value.kind == "CONNECTION"


@pytest.mark.parametrize("which", ["pg", "rw", "fe"])
def test_capability_refusal_is_explicit_and_side_effect_free(mocks, which):
    m = mocks(1); a = m[which][0]("cap")
    log = a.docker.log if hasattr(a.docker, "log") else []
    before = len(log); matrix = a.capability_matrix()["lifecycle"]
    for kind, state in matrix.items():
        if state == "UNSUPPORTED":
            with pytest.raises(CapabilityUnsupported):
                a.lifecycle(kind)
    assert len(log) == before
    with pytest.raises(CapabilityUnsupported):
        a.snapshot()


def test_process_group_timeout_kills_children(tmp_path):
    marker = tmp_path / "alive"
    rc, out, err, timed_out = run_group(["bash", "-c", f"(sleep 3; touch {marker}) & sleep 30"], 1.0)
    time.sleep(3.5)
    assert timed_out and not marker.exists()


def test_orphan_cleanup_removes_labelled_containers():
    class D:
        def __init__(self): self.log = []
        def run(self, a, t):
            self.log.append(a); return "c1\nc2\n" if a[0] == "ps" else ""
    d = D(); ids = orphan_cleanup(d, "RUN1")
    assert ids == ["c1", "c2"] and d.log[0][:3] == ["ps", "-aq", "--filter"] and d.log[1] == ["rm", "-f", "c1", "c2"]


def test_port_reuse_and_occupied_ports():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); busy = s.getsockname()[1]
    pa = PortAllocator(base=busy, span=5)
    p = pa.allocate(); assert p != busy
    pa.release(p); assert pa.allocate() == p
    s.close()


def test_resource_limits_and_slot_exclusivity(tmp_path):
    a = docker_run_args("n", "img@sha256:x", "0-7", 32, str(tmp_path), {41000: 5432}, {"cutwitness.run": "R"})
    for flag in ("--cpuset-cpus", "--memory", "--memory-swap", "--pids-limit"):
        assert flag in a
    assert a[a.index("--memory") + 1] == a[a.index("--memory-swap") + 1] == "32g" and "127.0.0.1:41000:5432" in a
    plan = ResourcePlan(34, 136); assert plan.slots == 4 and [plan.cpuset(i) for i in range(4)] == ["0-7", "8-15", "16-23", "24-31"]
    with pytest.raises(ValueError):
        plan.cpuset(4)
    assert len(set(plan.assignment(4))) == 4
    with pytest.raises(RuntimeError):
        ResourcePlan(4, 16).assignment(1)


def test_disk_guard_and_scratch_isolation(tmp_path):
    assert disk_ok(str(tmp_path), 0.0) and not disk_ok(str(tmp_path), 10 ** 9)
    d1 = scratch_dir(str(tmp_path), "u|1"); open(os.path.join(d1, "x"), "w").write("x")
    d2 = scratch_dir(str(tmp_path), "u|1"); assert d1 == d2 and not os.listdir(d2)


def test_container_digest_resume_check():
    from cutwitness.controller import digests_consistent
    assert digests_consistent({"pg_ivm": "sha256:a"}, {"pg_ivm": "sha256:a"})
    assert not digests_consistent({"pg_ivm": "sha256:a"}, {"pg_ivm": "sha256:b"})


def test_mock_evidence_can_never_satisfy_real_preflight():
    from cutwitness.conformance import run_conformance
    src = open(os.path.join(ROOT, "cutwitness", "controller.py")).read()
    assert "PROTOCOL_MOCK" not in src and "adapters.mocks" not in src
    assert run_conformance.__defaults__[-1] == "REAL"
