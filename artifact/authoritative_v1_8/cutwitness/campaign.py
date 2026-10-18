"""Crash-safe campaign engine: sealed run_id, append-only hash-chained journal, atomic commits, resume."""
from __future__ import annotations
import fcntl, hashlib, hmac, json, os, uuid
from typing import Callable, Dict, List
from .model import cjson, sha
from .crash import crash_point

STATUSES = ("PLANNED", "RUNNING", "COMMITTED", "FAILED_OPERATIONAL", "INVALID_SCIENTIFIC", "UNRESOLVED", "NOT_APPLICABLE")


def atomic_write(path: str, data: bytes) -> None:
    d = os.path.dirname(os.path.abspath(path)); os.makedirs(d, exist_ok=True)
    tmp = path + f".tmp.{os.getpid()}"
    with open(tmp, "wb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(d, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class JournalCorruption(Exception):
    pass


class Journal:
    GENESIS = "0" * 64

    def __init__(self, path: str):
        self.path = path
        self.recs: List[dict] = []
        self.torn_bytes = 0
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            lines = data.split(b"\n")
            tail = lines[-1]
            body = lines[:-1]
            for ln in body:
                if not ln.strip():
                    continue
                try:
                    self.recs.append(json.loads(ln))
                except json.JSONDecodeError:
                    raise JournalCorruption("unparseable interior journal line (tampering or media corruption)")
            if tail.strip():  # a final line without newline is an unacknowledged torn append: drop it, keep evidence
                self.torn_bytes = len(tail)
                with open(path + ".torn", "ab") as f:
                    f.write(tail + b"\n")
                with open(path, "r+b") as f:
                    f.truncate(len(data) - len(tail)); f.flush(); os.fsync(f.fileno())
            self.verify()
            if self.torn_bytes:
                self.append("TORN_TAIL_RECOVERED", {"bytes": self.torn_bytes})

    def head(self) -> str:
        return self.recs[-1]["hash"] if self.recs else self.GENESIS

    def verify(self):
        prev = self.GENESIS
        for i, r in enumerate(self.recs):
            body = {k: r[k] for k in ("seq", "prev", "kind", "payload")}
            if r["seq"] != i or r["prev"] != prev or r["hash"] != sha(body):
                raise JournalCorruption(f"hash chain broken at record {i}")
            prev = r["hash"]
        return True, len(self.recs), prev

    def append(self, kind: str, payload: dict) -> dict:
        import datetime
        payload = dict(payload, ts=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))  # runtime evidence
        body = {"seq": len(self.recs), "prev": self.head(), "kind": kind, "payload": payload}
        rec = dict(body); rec["hash"] = sha(body)
        line = (cjson(rec) + "\n").encode()
        from .crash import crash_point, torn_write_point
        with open(self.path, "ab") as f:
            if torn_write_point("during_journal_append", kind):
                f.write(line[: len(line) // 2]); f.flush(); os.fsync(f.fileno()); os._exit(77)
            f.write(line); f.flush(); os.fsync(f.fileno())
        self.recs.append(rec)
        return rec


class RunLock:
    def __init__(self, path: str):
        self.path = path; self.fd = None

    def __enter__(self):
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd); raise RuntimeError("another controller holds the run lock")
        return self

    def __exit__(self, *a):
        fcntl.flock(self.fd, fcntl.LOCK_UN); os.close(self.fd)


def hmac_seed(master_seed: str, *parts) -> int:
    msg = "|".join(str(p) for p in parts).encode()
    return int.from_bytes(hmac.new(master_seed.encode(), msg, hashlib.sha256).digest()[:8], "big")


class Campaign:
    def __init__(self, run_dir: str, config: dict, max_operational_retries: int = 2):
        self.run_dir = run_dir; os.makedirs(run_dir, exist_ok=True)
        self.config = config; self.config_digest = sha(config)
        self.retries = max_operational_retries
        self.journal = Journal(os.path.join(run_dir, "journal.jsonl"))
        self.meta_path = os.path.join(run_dir, "run_meta.json")

    def ensure_run_id(self) -> str:
        if os.path.exists(self.meta_path):
            meta = json.load(open(self.meta_path))
            if meta["config_digest"] != self.config_digest:
                raise RuntimeError("frozen configuration changed after run_id creation; refusing to continue")
            return meta["run_id"]
        meta = {"run_id": str(uuid.uuid4()), "config_digest": self.config_digest}
        atomic_write(self.meta_path, cjson(meta).encode())
        self.journal.append("RUN_SEALED", meta)
        return meta["run_id"]

    def status(self) -> Dict[str, dict]:
        st: Dict[str, dict] = {}
        for r in self.journal.recs:
            if r["kind"] == "UNIT":
                p = r["payload"]; s = st.setdefault(p["unit_id"], {"attempts": 0, "status": "PLANNED"})
                s["status"] = p["status"]
                if p["status"] == "RUNNING":
                    s["attempts"] += 1
                if "result" in p:
                    s["result"] = p["result"]
        return st

    def mark_not_applicable(self, unit_id: str, reason: str):
        if self.status().get(unit_id, {}).get("status") != "NOT_APPLICABLE":
            self.journal.append("UNIT", {"unit_id": unit_id, "status": "NOT_APPLICABLE", "reason": reason})

    def stage_done(self, stage: str) -> bool:
        return any(r["kind"] == "STAGE_DONE" and r["payload"]["stage"] == stage for r in self.journal.recs)

    def mark_stage(self, stage: str, info: dict):
        self.journal.append("STAGE_DONE", {"stage": stage, **info})

    def run_units(self, units: List[dict], executor: Callable[[dict], dict]) -> Dict[str, dict]:
        st = self.status()
        for u in units:
            s = st.get(u["unit_id"], {"attempts": 0, "status": "PLANNED"})
            if s["status"] in ("COMMITTED", "INVALID_SCIENTIFIC", "UNRESOLVED", "NOT_APPLICABLE"):
                continue
            if s["status"] == "RUNNING":  # crashed mid-unit: record the interrupted attempt, never overwrite it
                self.journal.append("UNIT", {"unit_id": u["unit_id"], "status": "FAILED_OPERATIONAL", "reason": "interrupted"})
            if s["attempts"] > self.retries:
                self.journal.append("UNIT", {"unit_id": u["unit_id"], "status": "FAILED_OPERATIONAL", "reason": "retry cap"})
                continue
            crash_point("before_unit_start")
            self.journal.append("UNIT", {"unit_id": u["unit_id"], "status": "RUNNING", "seed": u["seed"]})
            crash_point("after_running_entry")
            try:
                res = executor(u)
            except Exception as ex:
                self.journal.append("UNIT", {"unit_id": u["unit_id"], "status": "FAILED_OPERATIONAL",
                                             "reason": f"{type(ex).__name__}: {ex}"})
                continue
            blob = cjson(res).encode(); dg = hashlib.sha256(blob).hexdigest()
            atomic_write(os.path.join(self.run_dir, "results", f"{dg}.json"), blob)
            crash_point("after_output_before_commit")
            self.journal.append("UNIT", {"unit_id": u["unit_id"], "status": "COMMITTED", "result": dg})
            crash_point("after_commit")
        return self.status()


def run_units_parallel(camp: "Campaign", units: List[dict], fn, slots: int) -> Dict[str, dict]:
    """Parent-only journaling: RUNNING before dispatch, COMMITTED after the result is durably written."""
    if slots <= 1:
        return camp.run_units(units, lambda u: fn(u, 0))
    from concurrent.futures import ProcessPoolExecutor, FIRST_COMPLETED, wait
    st = camp.status(); todo = []
    for u in units:
        s = st.get(u["unit_id"], {"attempts": 0, "status": "PLANNED"})
        if s["status"] in ("COMMITTED", "INVALID_SCIENTIFIC", "UNRESOLVED", "NOT_APPLICABLE"):
            continue
        if s["status"] == "RUNNING":
            camp.journal.append("UNIT", {"unit_id": u["unit_id"], "status": "FAILED_OPERATIONAL", "reason": "interrupted"})
        if s["attempts"] > camp.retries:
            camp.journal.append("UNIT", {"unit_id": u["unit_id"], "status": "FAILED_OPERATIONAL", "reason": "retry cap"}); continue
        todo.append(u)
    free = list(range(slots)); running = {}
    with ProcessPoolExecutor(max_workers=slots) as ex:
        while todo or running:
            while todo and free:
                u = todo.pop(0); slot = free.pop(0)
                camp.journal.append("UNIT", {"unit_id": u["unit_id"], "status": "RUNNING", "seed": u["seed"], "slot": slot})
                running[ex.submit(fn, u, slot)] = (u, slot)
            done, _ = wait(list(running), return_when=FIRST_COMPLETED)
            for f in done:
                u, slot = running.pop(f); free.append(slot)
                try:
                    res = f.result()
                except Exception as e:
                    camp.journal.append("UNIT", {"unit_id": u["unit_id"], "status": "FAILED_OPERATIONAL", "reason": f"{type(e).__name__}: {e}"}); continue
                blob = cjson(res).encode(); dg = hashlib.sha256(blob).hexdigest()
                atomic_write(os.path.join(camp.run_dir, "results", f"{dg}.json"), blob)
                camp.journal.append("UNIT", {"unit_id": u["unit_id"], "status": "COMMITTED", "result": dg})
    return camp.status()
