"""Adapter conformance (S4): identical code runs against protocol mocks locally and real targets on the server."""
from __future__ import annotations
import random
from typing import Callable, Dict
from .adapters.base import SUPPORTED, AdapterFailure, CapabilityUnsupported
from .model import LIFECYCLE_KINDS, Txn, src
from .oracles import obs_digest, reference_obs
from .w3 import gen_history


def run_conformance(make_session: Callable, schema, views, pinned_probe: Dict[str, str], seed: int, n_histories: int = 3,
                    evidence_kind: str = "REAL") -> dict:
    """Returns {"ok": bool, "checks": [...]} ; any mismatch with the frozen capability matrix fails the gate."""
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)[:300]})

    s = make_session("conf0")
    try:
        probe = s.probe()
        for k, want in pinned_probe.items():
            chk(f"version:{k}", probe.get(k) == want, f"{probe.get(k)} vs {want}")
        rng = random.Random(seed)   # contract: make_session returns a ready session (schema and views created)
        h = gen_history(rng, schema, 6)
        for t in h:
            s.apply_transaction(t)
        s.flush()
        ref = reference_obs(views, src(schema, h))
        chk("incremental_equals_reference", obs_digest(s.read_views()) == obs_digest(ref))
        chk("clean_rebuild_equals_reference", obs_digest(s.clean_rebuild(src(schema, h))) == obs_digest(ref))
        for kind in LIFECYCLE_KINDS:
            state = s.capability_matrix()["lifecycle"][kind]
            if state == SUPPORTED:
                before = obs_digest(s.read_views())
                try:
                    s.lifecycle(kind); s.flush()
                    chk(f"lifecycle:{kind}:source_neutral", obs_digest(s.read_views()) == before)
                except AdapterFailure as e:
                    chk(f"lifecycle:{kind}:source_neutral", False, e)
            else:
                try:
                    s.lifecycle(kind); chk(f"lifecycle:{kind}:declared_unsupported", False, "operation did not refuse")
                except CapabilityUnsupported:
                    chk(f"lifecycle:{kind}:declared_unsupported", True)
    except AdapterFailure as e:
        chk("session", False, e)
    finally:
        try:
            s.destroy()
        except AdapterFailure:
            pass
    return {"ok": all(c["ok"] for c in checks) and bool(checks), "checks": checks, "evidence_kind": evidence_kind}
