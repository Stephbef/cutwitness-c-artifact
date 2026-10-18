"""Golden synthetic GTFS feed histories (engineering fixtures; deterministic zip bytes)."""
from __future__ import annotations
import io, zipfile
from typing import Dict, List, Tuple

HEAD = {"agency": "agency_id,agency_name,agency_url,agency_timezone", "routes": "route_id,agency_id,route_type",
        "trips": "route_id,service_id,trip_id", "stops": "stop_id,stop_name,parent_station",
        "stop_times": "trip_id,arrival_time,departure_time,stop_id,stop_sequence",
        "calendar": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date",
        "calendar_dates": "service_id,date,exception_type"}


def zip_feed(tables: Dict[str, List[str]]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_STORED) as z:
        for name in sorted(tables):
            zi = zipfile.ZipInfo(f"{name}.txt", date_time=(2020, 1, 1, 0, 0, 0))
            z.writestr(zi, "\n".join([HEAD[name]] + tables[name]) + "\n")
    return b.getvalue()


def base() -> Dict[str, List[str]]:
    return {"agency": ["A,Agency,http://a,Europe/Paris"], "routes": ["R1,A,3", "R2,A,0"],
            "trips": ["R1,WK,T1", "R1,WK,T2", "R2,WE,T3"], "stops": ["S1,One,", "S2,Two,P1", "S3,Three,P1", "P1,Parent,"],
            "stop_times": ["T1,08:00:00,08:00:00,S1,1", "T1,08:10:00,08:10:00,S2,2", "T2,09:00:00,09:00:00,S1,1",
                           "T2,09:20:00,09:20:00,S3,2", "T3,10:00:00,10:00:00,S2,1", "T3,10:30:00,10:30:00,S3,2"],
            "calendar": ["WK,1,1,1,1,1,0,0,20260101,20261231", "WE,0,0,0,0,0,1,1,20260101,20261231"],
            "calendar_dates": ["WK,20260501,2", "WE,20260502,1"]}


def _shift_departure(line: str) -> str:
    trip, arr, dep, stop, seq = line.split(",")
    h, m, sec = dep.split(":")
    return ",".join([trip, arr, f"{h}:{m}:{int(sec) + 5:02d}", stop, seq])


def history() -> List[Tuple[str, bytes]]:
    """Covers: ordinary update, revert, reapply, mass delete/reinsert, calendar/calendar_dates interaction, FK-sensitive change."""
    v0 = base()
    v1 = {k: list(v) for k, v in v0.items()}; v1["stop_times"][1] = "T1,08:12:00,08:12:00,S2,2"          # ordinary update
    v2 = {k: list(v) for k, v in v0.items()}                                                              # revert to v0
    v3 = {k: list(v) for k, v in v1.items()}                                                              # reapply v1
    v4 = {k: list(v) for k, v in v3.items()}; v4["stop_times"] = [_shift_departure(s) for s in v3["stop_times"]]  # mass delete/reinsert
    v5 = {k: list(v) for k, v in v4.items()}; v5["calendar_dates"] = ["WK,20260501,2", "WK,20260601,2", "WE,20260502,2"]    # calendar_dates
    v6 = {k: list(v) for k, v in v5.items()}                                                              # FK-sensitive: remove R2 with its trips/stop_times
    v6["routes"] = ["R1,A,3"]; v6["trips"] = ["R1,WK,T1", "R1,WK,T2"]; v6["stop_times"] = [s for s in v5["stop_times"] if not s.startswith("T3")]
    v7 = {k: list(v) for k, v in v6.items()}; v7["routes"].append("R3,A,3"); v7["trips"].append("R3,WK,T4")          # FK-sensitive add
    v7["stop_times"] += ["T4,11:00:00,11:00:00,S4,1"]; v7["stops"].append("S4,Four,")
    vs = [v0, v1, v1, v2, v3, v4, v5, v6, v7]                     # v1 repeated: identical consecutive snapshot collapses
    return [(f"2026-0{1 + i // 9}-{10 + i:02d}T00:00:00Z", zip_feed(v)) for i, v in enumerate(vs)]
