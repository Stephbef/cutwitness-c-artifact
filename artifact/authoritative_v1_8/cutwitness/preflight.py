"""Mandatory resource and campaign-duration preflight. Fails closed; there is no bypass flag."""
from __future__ import annotations
import os, shutil
from typing import Optional
from .matrix import build_matrix, legacy_v1_0_slot_hours, summarize

GIB = 2 ** 30


def measure(path: str = ".") -> dict:
    try:
        ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError):
        ram = 0
    try:
        cpus = len(os.sched_getaffinity(0))
    except AttributeError:
        cpus = os.cpu_count() or 0
    return {"AVAILABLE_VCPUS": cpus, "AVAILABLE_RAM_BYTES": ram, "AVAILABLE_DISK_BYTES": shutil.disk_usage(path).free}


def duration_preflight(cfg: dict, measured: Optional[dict] = None) -> dict:
    g = cfg["duration_gate"]; res = cfg["resources"]
    meas = measured if measured is not None else measure()
    rows = build_matrix(cfg); s = summarize(rows, g["overhead_hours"])
    usable_cpu = meas["AVAILABLE_VCPUS"] - g["reserve_vcpus"]
    usable_ram = meas["AVAILABLE_RAM_BYTES"] - g["reserve_ram_gib"] * GIB
    safe_cpu = max(0, usable_cpu // res["per_trial_cpus"])
    safe_ram = max(0, int(usable_ram // (res["per_trial_ram_gb"] * GIB)))
    safe_disk = max(0, int(meas["AVAILABLE_DISK_BYTES"] // (g["per_slot_disk_gib"] * GIB)))
    safe_port = max(0, g["port_span"] // 10)
    eff = min(res["configured_max_slots"], safe_cpu, safe_ram, safe_disk, safe_port)
    total = s["TOTAL_SEARCH_SLOT_HOURS"] + s["TOTAL_NONSEARCH_ESTIMATED_SLOT_HOURS"]
    hours = (total / eff) if eff > 0 else float("inf")
    days = hours / 24
    verdict = "PASS" if (eff > 0 and days <= g["max_campaign_days"]) else "BLOCKED"
    out = dict(s)
    out.update({k: meas[k] for k in ("AVAILABLE_VCPUS", "AVAILABLE_RAM_BYTES", "AVAILABLE_DISK_BYTES")})
    out.update({"CONFIGURED_MAX_SLOTS": res["configured_max_slots"], "SAFE_CPU_SLOTS": safe_cpu, "SAFE_RAM_SLOTS": safe_ram,
                "SAFE_DISK_SLOTS": safe_disk, "SAFE_PORT_SLOTS": safe_port, "EFFECTIVE_SLOTS": eff,
                "PROJECTED_WALL_HOURS": round(hours, 2) if eff > 0 else "INFINITE",
                "PROJECTED_WALL_DAYS": round(days, 2) if eff > 0 else "INFINITE",
                "MAX_CAMPAIGN_DAYS": g["max_campaign_days"],
                "EXPECTED_ARTIFACT_COUNT": s["TOTAL_UNITS"] + g["expected_witnesses_upper_bound"] + 16,
                "PROJECTED_ARTIFACT_BYTES": s["TOTAL_UNITS"] * g["est_bytes_per_unit"],
                "LEGACY_V1_0_PROJECTED_WALL_DAYS": round(legacy_v1_0_slot_hours(cfg) / max(eff, 1) / 24, 2),
                "CAMPAIGN_DURATION_PREFLIGHT": verdict})
    return out


def report_text(p: dict) -> str:
    return "".join(f"{k} = {p[k]}\n" for k in sorted(p))
