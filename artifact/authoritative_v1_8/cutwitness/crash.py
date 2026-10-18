"""Deterministic crash injection for resume testing: CW_CRASH_AT=<point>[@<n>] exits with code 77 at the n-th hit."""
import os

_hits = {}


def _armed(point: str) -> bool:
    spec = os.environ.get("CW_CRASH_AT", "")
    if not spec:
        return False
    name, _, n = spec.partition("@")
    if name != point:
        return False
    _hits[point] = _hits.get(point, 0) + 1
    return _hits[point] == int(n or 1)


def crash_point(point: str) -> None:
    if _armed(point):
        os._exit(77)


def torn_write_point(point: str, kind: str) -> bool:
    return kind == "UNIT" and _armed(point)
