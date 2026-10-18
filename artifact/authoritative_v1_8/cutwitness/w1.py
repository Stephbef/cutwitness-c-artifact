"""W1: real GTFS histories -> legal relational transaction streams.

Acquisition (Mobility Database API) runs only at server stage S3 with a token from the environment; every other
step is deterministic and locally testable on fixture feeds."""
from __future__ import annotations
import csv, hashlib, hmac, io, json, os, urllib.parse, urllib.request, zipfile
from typing import Dict, List, Optional, Tuple
from .model import Schema, Table, Txn, ZSet, apply_txn, empty_state, legal_state, state_digest
from .refmodel import Distinct, GroupAgg, Join, LeftJoin, Project, Scan, TopK, View

API = "https://api.mobilitydatabase.org"
GTFS_TABLES = ("agency", "routes", "trips", "stops", "stop_times", "calendar", "calendar_dates")
LICENSE_CLASSES = ("REDISTRIBUTABLE", "DERIVED_ONLY", "NO_REDISTRIBUTION")


def schema() -> Schema:
    return Schema([
        Table("agency", [("agency_id", "text", False), ("agency_timezone", "text", False)], pk=[0]),
        Table("routes", [("route_id", "text", False), ("agency_id", "text", False), ("route_type", "int", False)], pk=[0], fks=[([1], "agency", [0])]),
        Table("calendar", [("service_id", "text", False), ("days", "int", False), ("start_date", "int", False), ("end_date", "int", False)], pk=[0]),
        Table("calendar_dates", [("service_id", "text", False), ("date", "int", False), ("exception_type", "int", False)], pk=[0, 1]),
        Table("trips", [("trip_id", "text", False), ("route_id", "text", False), ("service_id", "text", False)], pk=[0], fks=[([1], "routes", [0])]),
        Table("stops", [("stop_id", "text", False), ("parent_station", "text", True)], pk=[0]),
        Table("stop_times", [("trip_id", "text", False), ("stop_sequence", "int", False), ("stop_id", "text", False), ("departure_s", "int", True)],
              pk=[0, 1], fks=[([0], "trips", [0]), ([2], "stops", [0])]),
    ])


def views(sch: Schema) -> List[View]:
    ar = {n: sch.tables[n].arity for n in sch.order}
    S = lambda p, t: Scan(f"{p}/s_{t}", t, ar[t])
    st_trip = lambda p: Join(f"{p}/j", Project(f"{p}/pst", S(p, "stop_times"), [0, 2, 3]), Project(f"{p}/ptr", S(p, "trips"), [0, 1]), 0, 0)
    return [
        View("w1_departures_per_stop", GroupAgg("w1a/g", Project("w1a/p", S("w1a", "stop_times"), [2, 3]), [0], [("COUNT", None), ("MIN", 1), ("MAX", 1)])),
        View("w1_first_last_per_route", GroupAgg("w1b/g", st_trip("w1b"), [4], [("MIN", 2), ("MAX", 2)])),
        View("w1_distinct_stops", Distinct("w1c/d", Project("w1c/p", S("w1c", "stop_times"), [2]))),
        View("w1_stops_without_service", LeftJoin("w1d/j", Project("w1d/ps", S("w1d", "stops"), [0]), Project("w1d/pt", S("w1d", "stop_times"), [2, 0]), 0, 0)),
        View("w1_busiest_trips_per_stop", TopK("w1e/t", Project("w1e/p", S("w1e", "stop_times"), [2, 3, 0, 1]), [0], [1], 3)),
        View("w1_service_exceptions", GroupAgg("w1f/g", Join("w1f/j", Project("w1f/pc", S("w1f", "calendar"), [0]), Project("w1f/pd", S("w1f", "calendar_dates"), [0, 2]), 0, 0), [0], [("COUNT", None), ("SUM", 2)])),
    ]


# ------------------------------------------------------------------ acquisition (server stage S3)

class CatalogClient:
    """Mobility Database API client. The refresh token is read from the environment and never logged or stored."""

    def __init__(self, token_env: str = "CUTWITNESS_W1_TOKEN", opener=None, timeout_s: float = 60):
        self.token_env, self.opener, self.timeout_s, self._access = token_env, opener or urllib.request.urlopen, timeout_s, None

    def _token(self) -> str:
        if self._access is None:
            rt = os.environ.get(self.token_env)
            if not rt:
                raise PermissionError(f"environment variable {self.token_env} is not set")
            req = urllib.request.Request(API + "/v1/tokens", data=json.dumps({"refresh_token": rt}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            with self.opener(req, timeout=self.timeout_s) as r:
                self._access = json.loads(r.read())["access_token"]
        return self._access

    def get(self, path: str, params: Optional[dict] = None):
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self._token()}"})
        with self.opener(req, timeout=self.timeout_s) as r:
            return json.loads(r.read())

    def download(self, url: str) -> bytes:
        with self.opener(urllib.request.Request(url), timeout=self.timeout_s) as r:
            return r.read()


def license_class(feed: dict) -> str:
    """Frozen rule: explicit open licences -> REDISTRIBUTABLE; any licence URL without an open marker -> DERIVED_ONLY;
    no licence information -> NO_REDISTRIBUTION (only hashes and derived results are packaged)."""
    lic = json.dumps(feed.get("source_info", {}) or {}).lower()
    if any(m in lic for m in ("creativecommons", "cc-by", "cc0", "odbl", "open data", "opendata", "public domain")):
        return "REDISTRIBUTABLE"
    if "license" in lic or "licence" in lic:
        return "DERIVED_ONLY"
    return "NO_REDISTRIBUTION"


def select_regions(feeds: List[dict], master_seed: str, n_validation: int = 8, n_test: int = 16,
                   min_datasets: int = 12) -> Tuple[List[str], List[str]]:
    """Frozen, data-independent rule: eligible = active GTFS feeds with >= min_datasets historical datasets;
    order by HMAC-SHA256(master_seed, feed_id); first n_validation -> VALIDATION, next n_test -> TEST (disjoint)."""
    elig = sorted({f["id"] for f in feeds if f.get("status", "active") == "active" and f.get("n_datasets", 0) >= min_datasets})
    rank = sorted(elig, key=lambda i: hmac.new(master_seed.encode(), i.encode(), hashlib.sha256).hexdigest())
    if len(rank) < n_validation + n_test:
        raise RuntimeError(f"only {len(rank)} eligible feeds; frozen design needs {n_validation + n_test}")
    return rank[:n_validation], rank[n_validation:n_validation + n_test]


class SplitFirewall:
    """VALIDATION/TEST firewall: TEST material is unreadable until the TEST stage is explicitly opened."""

    def __init__(self, validation: List[str], test: List[str]):
        if set(validation) & set(test):
            raise ValueError("VALIDATION and TEST overlap")
        self.validation, self.test, self.test_open = list(validation), list(test), False

    def open_test(self):
        self.test_open = True

    def check(self, feed_id: str):
        if feed_id in self.test and not self.test_open:
            raise PermissionError(f"TEST feed {feed_id} accessed before the TEST stage")
        if feed_id not in self.test and feed_id not in self.validation:
            raise PermissionError(f"feed {feed_id} is outside the frozen split")


# ------------------------------------------------------------------ normalization, sampling, versioning

def _read_csv(z: zipfile.ZipFile, name: str) -> List[dict]:
    members = {os.path.basename(m).lower(): m for m in z.namelist() if not m.endswith("/")}
    m = members.get(name + ".txt")
    if m is None:
        return []
    text = z.read(m).decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _secs(t: str) -> Optional[int]:
    t = (t or "").strip()
    if not t:
        return None
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


def _ascii(s: str) -> str:
    return (s or "").encode("ascii", "replace").decode()


def normalize(zip_bytes: bytes, sample_routes: int, sample_seed: str) -> Dict[str, ZSet]:
    """GTFS zip -> relational state; deterministic route sample keeps FK closure (agencies, trips, stops, stop_times)."""
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    raw = {t: _read_csv(z, t) for t in GTFS_TABLES}
    routes = sorted({_ascii(r["route_id"]) for r in raw["routes"]})
    keep = set(sorted(routes, key=lambda r: hmac.new(sample_seed.encode(), r.encode(), hashlib.sha256).hexdigest())[:sample_routes])
    st = {t: ZSet() for t in GTFS_TABLES}
    default_agency = _ascii(raw["agency"][0].get("agency_id") or "default") if raw["agency"] else "default"
    agencies = {}
    for a in raw["agency"]:
        agencies[_ascii(a.get("agency_id") or default_agency)] = _ascii(a.get("agency_timezone", ""))
    used_agencies, trips, services = set(), set(), set()
    for r in raw["routes"]:
        rid = _ascii(r["route_id"])
        if rid in keep:
            ag = _ascii(r.get("agency_id") or default_agency); used_agencies.add(ag)
            st["routes"].add_row((rid, ag, int(r.get("route_type") or 3)), 1)
    for a in sorted(used_agencies):
        st["agency"].add_row((a, agencies.get(a, "")), 1)
    for t in raw["trips"]:
        if _ascii(t["route_id"]) in keep:
            tid = _ascii(t["trip_id"]); trips.add(tid); services.add(_ascii(t["service_id"]))
            st["trips"].add_row((tid, _ascii(t["route_id"]), _ascii(t["service_id"])), 1)
    stops_used = set(); seen_pk = set()
    for s in raw["stop_times"]:
        tid = _ascii(s["trip_id"])
        if tid in trips:
            pk = (tid, int(s["stop_sequence"]))
            if pk in seen_pk:
                continue
            seen_pk.add(pk); sid = _ascii(s["stop_id"]); stops_used.add(sid)
            st["stop_times"].add_row((tid, pk[1], sid, _secs(s.get("departure_time", ""))), 1)
    for s in raw["stops"]:
        sid = _ascii(s["stop_id"])
        if sid in stops_used:
            st["stops"].add_row((sid, _ascii(s.get("parent_station") or "") or None), 1)
    missing = stops_used - {r[0] for r in st["stops"].d}
    for sid in sorted(missing):
        st["stops"].add_row((sid, None), 1)
    for c in raw["calendar"]:
        sid = _ascii(c["service_id"])
        if sid in services:
            days = sum(int(c.get(d, "0") or 0) << i for i, d in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")))
            st["calendar"].add_row((sid, days, int(c["start_date"]), int(c["end_date"])), 1)
    seen_cd = set()
    for c in raw["calendar_dates"]:
        sid = _ascii(c["service_id"])
        if sid in services:
            k = (sid, int(c["date"]))
            if k not in seen_cd:
                seen_cd.add(k); st["calendar_dates"].add_row((sid, k[1], int(c["exception_type"])), 1)
    return st


def logical_versions(snapshots: List[Tuple[str, Dict[str, ZSet]]]) -> List[dict]:
    """snapshots: [(downloaded_at, state)] sorted by time. Consecutive identical contents collapse; recurrences
    (return to an earlier content) are kept as new transitions and flagged."""
    out, seen = [], {}
    for when, stt in sorted(snapshots, key=lambda s: s[0]):
        dg = state_digest(stt)
        if out and out[-1]["digest"] == dg:
            continue
        out.append({"at": when, "digest": dg, "state": stt, "recurrence_of": seen.get(dg)})
        seen.setdefault(dg, len(out) - 1)
    return out


def diff_transactions(sch: Schema, versions: List[dict]) -> List[Txn]:
    """One legal transaction per consecutive logical-version transition (row-level Z-set difference)."""
    x = empty_state(sch); h = []
    for v in versions:
        d = {t: v["state"][t] - x[t] for t in sch.order}
        txn = Txn(d)
        if txn.is_empty():
            continue
        x1 = apply_txn(x, txn)
        ok, why = legal_state(sch, x1)
        if not ok:
            raise ValueError(f"version {v['at']} produces an illegal state: {why}")
        h.append(txn); x = x1
    return h


def provenance(feed_id: str, datasets: List[dict], versions: List[dict], lic: str) -> dict:
    return {"feed_id": feed_id, "license_class": lic,
            "datasets": [{"id": d.get("id"), "downloaded_at": d.get("downloaded_at"), "sha256": d.get("sha256")} for d in datasets],
            "logical_versions": [{"at": v["at"], "digest": v["digest"], "recurrence_of": v["recurrence_of"]} for v in versions]}


def materialize_feed(client: CatalogClient, feed_id: str, firewall: SplitFirewall, sample_routes: int, seed: str,
                     max_versions: int, out_dir: str) -> dict:
    """Server stage S3: fetch datasets, hash, normalize, version, diff. Returns the feed manifest (no token, no raw data
    unless the licence class permits redistribution)."""
    firewall.check(feed_id)
    feed = client.get(f"/v1/gtfs_feeds/{feed_id}")
    dsets = sorted(client.get(f"/v1/gtfs_feeds/{feed_id}/datasets", {"limit": 500}), key=lambda d: d.get("downloaded_at", ""))
    snaps, recs = [], []
    for d in dsets[-max_versions:]:
        blob = client.download(d["hosted_url"]); h = hashlib.sha256(blob).hexdigest()
        if d.get("hash") and d["hash"] != h:
            raise ValueError(f"dataset {d.get('id')} hash mismatch")
        recs.append({"id": d.get("id"), "downloaded_at": d.get("downloaded_at"), "sha256": h})
        snaps.append((d.get("downloaded_at", ""), normalize(blob, sample_routes, seed)))
        if license_class(feed) == "REDISTRIBUTABLE":
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, f"{feed_id}_{h[:16]}.zip"), "wb") as f:
                f.write(blob)
    versions = logical_versions(snaps)
    sch = schema(); txns = diff_transactions(sch, versions)
    return {"provenance": provenance(feed_id, recs, versions, license_class(feed)), "n_transactions": len(txns),
            "history": [t.canon() for t in txns]}
