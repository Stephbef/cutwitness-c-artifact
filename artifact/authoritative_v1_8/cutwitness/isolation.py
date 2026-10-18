"""Resource isolation: cpusets, memory limits, scratch dirs, process groups, timeouts, ports, orphan cleanup."""
from __future__ import annotations
import os, shutil, signal, socket, subprocess
from typing import Dict, List, Optional


class ResourcePlan:
    def __init__(self, host_cpus: int, host_ram_gb: float, per_trial_cpus: int = 8, per_trial_ram_gb: int = 32,
                 reserve_cpus: int = 2, reserve_ram_gb: int = 8):
        self.cpus, self.ram, self.pc, self.pr = host_cpus, host_ram_gb, per_trial_cpus, per_trial_ram_gb
        self.slots = max(0, min((host_cpus - reserve_cpus) // per_trial_cpus, int((host_ram_gb - reserve_ram_gb) // per_trial_ram_gb)))

    def cpuset(self, slot: int) -> str:
        if not 0 <= slot < self.slots:
            raise ValueError(f"slot {slot} outside [0, {self.slots})")
        a = slot * self.pc
        return f"{a}-{a + self.pc - 1}"

    def assignment(self, n_units: int) -> List[int]:
        """Exclusive slot per concurrent unit; units beyond the slot count wait (never oversubscribe)."""
        if self.slots == 0:
            raise RuntimeError("no resource slot: host below per-trial envelope")
        return [i % self.slots for i in range(n_units)]


def docker_run_args(name: str, image: str, cpuset: str, mem_gb: int, scratch: str, ports: Dict[int, int],
                    labels: Dict[str, str], command: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None) -> List[str]:
    a = ["run", "-d", "--name", name, "--cpuset-cpus", cpuset, "--memory", f"{mem_gb}g", "--memory-swap", f"{mem_gb}g",
         "--pids-limit", "8192", "--ulimit", "nofile=65536:65536", "-v", f"{scratch}:/data"]
    for hp, cp in sorted(ports.items()):
        a += ["-p", f"127.0.0.1:{hp}:{cp}"]
    for k, v in sorted(labels.items()):
        a += ["--label", f"{k}={v}"]
    for k, v in sorted((env or {}).items()):
        a += ["-e", f"{k}={v}"]
    return a + [image] + (command or [])


class PortAllocator:
    def __init__(self, base: int = 41000, span: int = 2000, probe=None):
        self.base, self.span, self.taken = base, span, set()
        self.probe = probe or _port_free

    def allocate(self) -> int:
        for p in range(self.base, self.base + self.span):
            if p not in self.taken and self.probe(p):
                self.taken.add(p); return p
        raise RuntimeError("no free port in range")

    def release(self, p: int):
        self.taken.discard(p)


def _port_free(p: int) -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p)); return True
    except OSError:
        return False
    finally:
        s.close()


def run_group(cmd: List[str], timeout_s: float, cwd: Optional[str] = None, env: Optional[dict] = None):
    """Run in a new process group; on timeout kill the whole group. Returns (rc, stdout, stderr, timed_out)."""
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout_s); return p.returncode, out.decode(), err.decode(), False
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL); out, err = p.communicate(); return -9, out.decode(), err.decode(), True


def scratch_dir(root: str, unit_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in unit_id)
    d = os.path.join(root, "scratch", safe)
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d); return d


def orphan_cleanup(docker, run_id: str, timeout_s: float = 60) -> List[str]:
    out = docker.run(["ps", "-aq", "--filter", f"label=cutwitness.run={run_id}"], timeout_s)
    ids = [x for x in out.split() if x]
    if ids:
        docker.run(["rm", "-f"] + ids, timeout_s)
    return ids


def disk_ok(path: str, need_gb: float) -> bool:
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 2**30 >= need_gb
