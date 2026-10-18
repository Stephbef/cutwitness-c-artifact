"""Write manifests/PREEXECUTION_MANIFEST.json and SHA256SUMS for the package tree (run last, after all files are final)."""
import hashlib, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
SKIP_DIRS = {".git", "__pycache__", ".venv", ".pytest_cache", "runs"}
ROLE = [("cutwitness/", "active source", "scientific"), ("tests/", "test suite", "verification"), ("campaign/", "frozen configuration", "scientific"),
        ("science/", "scientific freeze and amendments", "scientific"), ("vendor/", "dependency wheelhouse and locks", "operational"),
        ("server/", "target deployment definitions", "operational"), ("tools/", "build and verification tools", "operational"),
        ("manifests/", "pins and manifests", "operational"), ("qa/", "internal QA evidence", "verification"), ("legacy/", "provenance pointer", "provenance")]


def role(rel):
    for pre, r, c in ROLE:
        if rel.startswith(pre):
            return r, c
    return "top-level document or entry point", "operational"


def tree_digest(files, prefix=""):
    return hashlib.sha256("".join(f"{h} {p}\n" for p, h in files if p.startswith(prefix)).encode()).hexdigest()


def main(root: str = None):
    global ROOT
    ROOT = root or ROOT
    files = []
    for d, dirs, fs in os.walk(ROOT):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for f in sorted(fs):
            rel = os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, "/")
            if rel in ("manifests/PREEXECUTION_MANIFEST.json", "SHA256SUMS") or rel.endswith(".pyc") or rel.startswith(".git/"):
                continue
            files.append((rel, hashlib.sha256(open(os.path.join(ROOT, rel), "rb").read()).hexdigest()))
    files.sort()
    import importlib, sys as _s
    from cutwitness.controller import code_digest
    from cutwitness.config import load, digest
    cfg = load(os.path.join(ROOT, "campaign", "FROZEN_CAMPAIGN.yaml"))
    h = lambda p: hashlib.sha256(open(os.path.join(ROOT, p), "rb").read()).hexdigest()
    man = {"schema": "cutwitness-c/manifest/1",
           "files": [{"path": p, "bytes": os.path.getsize(os.path.join(ROOT, p)), "sha256": s, "role": role(p)[0], "class": role(p)[1]} for p, s in files],
           "digests": {"repository_tree": tree_digest(files), "active_source": code_digest(ROOT), "test_suite": tree_digest(files, "tests/"),
                       "campaign_config": digest(cfg), "dependency_lock": h("vendor/requirements.lock"),
                       "target_freeze": h("manifests/TARGET_VERSION_FREEZE.json"), "scientific_freeze": h("science/SCIENTIFIC_FREEZE_CUTWITNESS_C.md"),
                       "one_shot_amendment": h("science/ONE_SHOT_EXECUTION_AMENDMENT.md"),
                       "feasibility_amendment_v1_1": h("science/CUTWITNESS_C_PREEXECUTION_FEASIBILITY_AMENDMENT_v1_1.md"),
                       "analysis_spec_v2": h("science/ANALYSIS_SPEC_v2.md"), "adjudication_protocol_v1": h("ROOT_CAUSE_ADJUDICATION_PROTOCOL_v1.md"),
                       "analysis_spec_v3": h("science/ANALYSIS_SPEC_v3.md"), "analysis_spec_v4": h("science/ANALYSIS_SPEC_v4.md"), "analysis_spec_v5": h("science/ANALYSIS_SPEC_v5.md"), "analysis_spec_v6": h("science/ANALYSIS_SPEC_v6.md"), "analysis_spec_v7": h("science/ANALYSIS_SPEC_v7.md"), "amendment_v1_8_deletion_matched": h("PREEXECUTION_AMENDMENT_V1_8_DELETION_MATCHED_CONTROL.md"), "deletion_matched_contract": h("DELETION_MATCHED_CONTROL_CONTRACT.md"), "e3_amendment": h("E3_ATTRIBUTION_AMENDMENT.md"), "rho_instrumentation_amendment": h("EQUIVALENCE_SAMPLING_INSTRUMENTATION_AMENDMENT_v1.md"), "adjudication_protocol_v4": h("ROOT_CAUSE_ADJUDICATION_PROTOCOL_v4.md"), "amendment_v1_4": h("SCIENTIFIC_AMENDMENT_v1_4.md"), "matching_contract": h("RANDOM_SUFFIX_MATCHING_CONTRACT.md"), "adjudication_protocol_v3": h("ROOT_CAUSE_ADJUDICATION_PROTOCOL_v3.md"), "adjudication_protocol_v2": h("ROOT_CAUSE_ADJUDICATION_PROTOCOL_v2.md"),
                       "attribution_amendment_v1_2": h("CUTWITNESS_C_PREEXECUTION_ATTRIBUTION_AMENDMENT_v1_2.md"),
                       "evidence_registry": h("MANUSCRIPT_EVIDENCE_REGISTRY.csv"), "patch2_record": h("PATCH2_RECORD.json")}}
    json.dump(man, open(os.path.join(ROOT, "manifests", "PREEXECUTION_MANIFEST.json"), "w"), indent=1, sort_keys=True)
    open(os.path.join(ROOT, "SHA256SUMS"), "w").write("".join(f"{s}  {p}\n" for p, s in files))
    print("manifest files", len(files), json.dumps(man["digests"], sort_keys=True))


if __name__ == "__main__":
    main()
