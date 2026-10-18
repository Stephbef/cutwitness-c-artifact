"""Root-cause adjudication ledger schema and validator (ROOT_CAUSE_ADJUDICATION_PROTOCOL_v1)."""
from __future__ import annotations
import csv, json, os, sys
from typing import Dict, List

LEDGER_COLUMNS = ["root_cause_id", "witness_ids", "target", "workload", "operator", "primary_class", "latent", "lifecycle_annotation",
                  "adjudication_basis", "merge_evidence", "methods_detecting", "confidence_status", "latent_attribution",
                  "adjudicator_A_class", "adjudicator_B_class", "agreement", "resolution", "adjudicator_independence"]
LATENT_ATTRIBUTION = ("HISTORY_CONDITIONED_LATENT", "CONTINUATION_TRIGGERED", "UNRESOLVED_ATTRIBUTION", "NOT_LATENT")
EXTERNAL_COLUMNS = ["report_id", "root_cause_ids", "target", "tracker_reference", "status", "status_date", "note"]
PRIMARY_CLASSES = ("final-cut", "path-convergence", "latent-continuation", "lifecycle-sensitive")
CONFIDENCE = ("ADJUDICATED", "UNRESOLVED_KEPT_SEPARATE")
EXTERNAL_STATUSES = ("NEW", "DUPLICATE", "KNOWN", "INVALID", "EXPECTED", "ACKNOWLEDGED", "FIXED", "UNRESOLVED")
FORBIDDEN_SOLE_BASIS = ("operator family", "error text", "lifecycle event", "similar output")


def validate_ledger(rows: List[dict], witnesses: Dict[str, dict]) -> List[str]:
    err, seen_rc, seen_w = [], set(), {}
    for i, r in enumerate(rows):
        if set(LEDGER_COLUMNS) - set(r):
            err.append(f"row {i}: missing columns {sorted(set(LEDGER_COLUMNS) - set(r))}"); continue
        rc = r["root_cause_id"]
        if not rc or rc in seen_rc:
            err.append(f"row {i}: empty or duplicate root_cause_id {rc!r}")
        seen_rc.add(rc)
        wids = [x for x in r["witness_ids"].split(";") if x]
        if not wids:
            err.append(f"{rc}: no witness")
        for wid in wids:
            if wid not in witnesses:
                err.append(f"{rc}: unknown witness {wid}")
            elif witnesses[wid].get("status") != "NEW":
                err.append(f"{rc}: witness {wid} is not a reproduced witness (status {witnesses[wid].get('status')})")
            if wid in seen_w:
                err.append(f"{rc}: witness {wid} already assigned to {seen_w[wid]}")
            seen_w[wid] = rc
        if r["primary_class"] not in PRIMARY_CLASSES:
            err.append(f"{rc}: primary_class {r['primary_class']!r}")
        if r["confidence_status"] not in CONFIDENCE:
            err.append(f"{rc}: confidence_status {r['confidence_status']!r}")
        if str(r["latent"]).lower() not in ("true", "false"):
            err.append(f"{rc}: latent must be true/false")
        la = r.get("latent_attribution", "")
        if la not in LATENT_ATTRIBUTION:
            err.append(f"{rc}: latent_attribution {la!r}")
        elif (str(r["latent"]).lower() == "true") != (la != "NOT_LATENT"):
            err.append(f"{rc}: latent flag and latent_attribution disagree")
        if r.get("agreement") not in ("AGREE", "DISAGREE"):
            err.append(f"{rc}: agreement must be AGREE or DISAGREE")
        elif r["agreement"] == "AGREE" and not (r.get("adjudicator_A_class") == r.get("adjudicator_B_class") == r["primary_class"]):
            err.append(f"{rc}: AGREE requires both adjudicator classes to equal primary_class")
        elif r["agreement"] == "DISAGREE" and not r.get("resolution", "").strip():
            err.append(f"{rc}: DISAGREE requires a recorded resolution")
        if r.get("adjudicator_independence") not in ("AUTHORS_ONLY", "INCLUDES_EXTERNAL"):
            err.append(f"{rc}: adjudicator_independence must be AUTHORS_ONLY or INCLUDES_EXTERNAL")
        if not r["adjudication_basis"].strip():
            err.append(f"{rc}: empty adjudication_basis")
        if len(wids) > 1:
            ev = r["merge_evidence"].strip().lower()
            if not ev:
                err.append(f"{rc}: merge of {len(wids)} witnesses without merge_evidence")
            elif any(ev == b or ev == b + " matches" for b in FORBIDDEN_SOLE_BASIS):
                err.append(f"{rc}: merge justified only by a forbidden sole basis ({ev})")
            if len({witnesses[w]["target"] for w in wids if w in witnesses}) > 1:
                err.append(f"{rc}: a root cause cannot span targets")
    return err


def validate_external(rows: List[dict], root_cause_ids) -> List[str]:
    err = []
    for i, r in enumerate(rows):
        if set(EXTERNAL_COLUMNS) - set(r):
            err.append(f"report row {i}: missing columns"); continue
        if r["status"] not in EXTERNAL_STATUSES:
            err.append(f"{r['report_id']}: status {r['status']!r}")
        for rc in [x for x in r["root_cause_ids"].split(";") if x]:
            if rc not in root_cause_ids:
                err.append(f"{r['report_id']}: references unknown root cause {rc} (reports cannot create root causes)")
    return err


def main(argv=None) -> int:
    a = argv or sys.argv[1:]
    ledger, wdir = a[0], a[1]
    witnesses = {}
    for f in os.listdir(wdir):
        if f.endswith(".json"):
            w = json.load(open(os.path.join(wdir, f))); witnesses[w["id"]] = w
    rows = list(csv.DictReader(open(ledger)))
    errs = validate_ledger(rows, witnesses)
    if len(a) > 2:
        errs += validate_external(list(csv.DictReader(open(a[2]))), {r["root_cause_id"] for r in rows})
    for e in errs:
        print("ADJUDICATION_ERROR", e)
    print("ADJUDICATION_LEDGER", "VALID" if not errs else "INVALID", len(rows), "root causes")
    return 0 if not errs else 5


if __name__ == "__main__":
    sys.exit(main())


POST_RUN = "POST-RUN MANUAL/ADJUDICATED"


def validate_registry(rows) -> list:
    """Producer classes must match reality: the root-cause ledger exists only after manual adjudication."""
    err = []
    for r in rows:
        art = r.get("analysis_artifact", "") + " " + r.get("raw_artifact", "")
        if "root_cause_adjudication_ledger.csv" in r.get("analysis_artifact", "") and r.get("producer_status") != POST_RUN:
            err.append(f"{r['manuscript_location']} / {r['metric_name']}: names the adjudication ledger but is classed {r.get('producer_status')!r}")
        if r.get("producer_status") == "MISSING":
            err.append(f"{r['manuscript_location']} / {r['metric_name']}: no producer")
        if "ablate_no_suffix" in art and "latent" in r.get("metric_name", "").lower() and "statistic" in r.get("metric_name", "").lower():
            err.append(f"{r['manuscript_location']}: inferential latent statistic for a suffix-free arm (structurally impossible)")
    return err


def agreement_stats(rows) -> dict:
    """Raw agreement and Cohen's kappa between the two adjudicators (kappa only when >= 2 categories occur)."""
    pairs = [(r["adjudicator_A_class"], r["adjudicator_B_class"]) for r in rows]
    n = len(pairs)
    if not n:
        return {"n": 0, "raw_agreement": None, "cohens_kappa": None}
    po = sum(a == b for a, b in pairs) / n
    cats = sorted({c for p in pairs for c in p})
    if len(cats) < 2:
        return {"n": n, "raw_agreement": po, "cohens_kappa": None}
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    return {"n": n, "raw_agreement": po, "cohens_kappa": (po - pe) / (1 - pe) if pe < 1 else None}
