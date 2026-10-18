"""Adapter contract, capability states and failure classification."""
from __future__ import annotations
import time
from typing import Dict, List, Optional
from ..model import LIFECYCLE_KINDS, Txn, ZSet

SUPPORTED, UNSUPPORTED = "SUPPORTED", "UNSUPPORTED"
FAILURE_KINDS = ("TIMEOUT", "CONNECTION", "MALFORMED_RESPONSE", "TARGET_ERROR", "READINESS", "VERSION_MISMATCH",
                 "UNSUPPORTED", "CANONICALIZATION")


class AdapterFailure(Exception):
    def __init__(self, kind: str, detail: str):
        assert kind in FAILURE_KINDS, kind
        super().__init__(f"{kind}: {detail}"); self.kind = kind; self.detail = detail


class CapabilityUnsupported(AdapterFailure):
    def __init__(self, op: str, why: str):
        super().__init__("UNSUPPORTED", f"{op}: {why}"); self.op = op


def wait_until(pred, timeout_s: float, interval_s: float, what: str, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout_s
    last = None
    while True:
        try:
            if pred():
                return True
        except AdapterFailure as e:
            if e.kind not in ("CONNECTION", "TIMEOUT", "READINESS"):
                raise                       # permanent protocol/target errors are never retried into a TIMEOUT
            last = e
        if clock() >= deadline:
            raise AdapterFailure("READINESS" if what.startswith("ready") else "TIMEOUT", f"{what} not reached in {timeout_s}s; last={last}")
        sleep(interval_s)


class Adapter:
    """Contract used by the campaign. Every lifecycle kind is SUPPORTED or raises CapabilityUnsupported."""
    target = "abstract"
    LIFECYCLE: Dict[str, str] = {}
    OPS: Dict[str, str] = {}

    def capability_matrix(self) -> dict:
        return {"target": self.target, "ops": dict(self.OPS),
                "lifecycle": {k: self.LIFECYCLE.get(k, UNSUPPORTED) for k in LIFECYCLE_KINDS}}

    def lifecycle(self, kind: str):
        if self.LIFECYCLE.get(kind) != SUPPORTED:
            raise CapabilityUnsupported(kind, f"not supported by {self.target}")
        return {"RESTART": self.restart, "KILL_RECOVER": self.kill_recover, "CHECKPOINT": self.checkpoint,
                "RESTORE_LATEST": self.restore_latest, "RESCALE": self.rescale, "UPGRADE": self.upgrade,
                "REPLACE_VIEW_IDENTICAL": self.replace_view_identical, "COMPACT": self.compact}[kind]()

    def snapshot(self):
        raise CapabilityUnsupported("SNAPSHOT", "real targets are replayed from the trie root instead of forked")

    # the following raise for unsupported kinds; subclasses override supported ones
    def restart(self): raise CapabilityUnsupported("RESTART", self.target)
    def kill_recover(self): raise CapabilityUnsupported("KILL_RECOVER", self.target)
    def checkpoint(self): raise CapabilityUnsupported("CHECKPOINT", self.target)
    def restore_latest(self): raise CapabilityUnsupported("RESTORE_LATEST", self.target)
    def rescale(self): raise CapabilityUnsupported("RESCALE", self.target)
    def upgrade(self): raise CapabilityUnsupported("UPGRADE", self.target)
    def replace_view_identical(self): raise CapabilityUnsupported("REPLACE_VIEW_IDENTICAL", self.target)
    def compact(self): raise CapabilityUnsupported("COMPACT", self.target)
