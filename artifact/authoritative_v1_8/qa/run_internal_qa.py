"""Internal QA beyond unit tests. Writes qa/QA_EVIDENCE.json (engineering evidence, not campaign evidence)."""
import json, os, random, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from cutwitness.model import src, prefix_legal
from cutwitness.oracles import reference_obs, duckdb_obs, obs_digest, judge, triage
from cutwitness.toyengine import ToyEngine, FAULTS, IN_MODEL, ADVERSARIAL, reset_adversarial
from cutwitness.w3 import gen_schema, gen_views, gen_history
from cutwitness.suffix import synthesize, SuffixUnsupported
from cutwitness import transforms as T
from cutwitness.campaign import Journal

ev = {"label": "ENGINEERING VALIDATION ONLY \u2014 NOT SCIENTIFIC RESULTS"}
t0 = time.time()
# 1. reference vs DuckDB differential corpus
N = int(os.environ.get("QA_DIFF_N", "300")); mism = []
for seed in range(N):
    rng = random.Random(20000 + seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, rng.randint(3, 20))
    x = src(s, h); r = reference_obs(vs, x); d = duckdb_obs(s, vs, x)
    for v in vs:
        if r[v.name].digest() != d[v.name].digest():
            mism.append((seed, v.name))
ev["reference_vs_duckdb"] = {"states": N, "view_evaluations": N * 6, "mismatches": len(mism), "examples": mism[:5]}
# 2. correct engine: zero false divergences (with lifecycle, suffixes)
M = int(os.environ.get("QA_CORRECT_N", "1500")); false_div = 0; kinds = sorted(ToyEngine.caps["lifecycle"])
for seed in range(M):
    rng = random.Random(40000 + seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, rng.randint(2, 12))
    for _ in range(rng.randint(0, 3)):
        h, _ = T.insert_lifecycle(s, h, rng.randrange(len(h)), rng.choice(kinds))
    suf = []
    g = vs[0]; keys = sorted(g.top.key_rows(src(s, h), {}), key=repr)
    if keys:
        try:
            suf, _ = synthesize(s, g, src(s, h), keys[0])
        except SuffixUnsupported:
            suf = []
    if judge(lambda: ToyEngine(s, vs, "NONE"), s, vs, h, suf, use_o3=False)["diverges"]:
        false_div += 1
ev["correct_engine"] = {"histories": M, "false_divergences": false_div}
# 3. seeded-fault matrix: random histories with/without suffix
mat = {}
for f in FAULTS[1:]:
    det_cut = det_suf = cand = trials = 0; classes = {}
    for seed in range(40):
        rng = random.Random(60000 + seed); s = gen_schema(rng); vs = gen_views(rng, s); h = gen_history(rng, s, 10)
        if f == "F8_LIFECYCLE_RESTORE":
            h, _ = T.insert_lifecycle(s, h, len(h) - 1, "RESTART")
        fac = lambda: ToyEngine(s, vs, f); trials += 1
        reset_adversarial(seed)
        vc = judge(fac, s, vs, h, use_o3=False)
        suf = []
        for v in vs:
            if v.exposed():
                ks = sorted(v.top.key_rows(src(s, h), {}), key=repr)
                if ks:
                    try:
                        suf, _ = synthesize(s, v, src(s, h), ks[0]); break
                    except SuffixUnsupported:
                        continue
        vsuf = judge(fac, s, vs, h, suf, use_o3=False)
        det_cut += vc["diverges"]; det_suf += vsuf["diverges"]
        if vsuf["diverges"]:
            tr = triage(fac, s, vs, h, suf); classes[tr["class"]] = classes.get(tr["class"], 0) + 1; cand += tr.get("candidate", False)
    mat[f] = {"in_model": f in IN_MODEL, "nondeterminism_control": f == "F11_NONDETERMINISM" or f in ADVERSARIAL, "trials": trials, "detected_at_cut": det_cut, "detected_with_suffix": det_suf,
              "candidates": cand, "triage": classes}
ev["seeded_fault_matrix_random"] = mat
ev["wall_s"] = round(time.time() - t0, 1)
json.dump(ev, open(os.path.join(ROOT, "qa", "QA_EVIDENCE.json"), "w"), indent=1, sort_keys=True, ensure_ascii=False)
print(json.dumps({k: (v if k != "seeded_fault_matrix_random" else {f: (m["detected_at_cut"], m["detected_with_suffix"], m["candidates"], m["triage"]) for f, m in v.items()}) for k, v in ev.items()}, indent=1, sort_keys=True))
