"""W1 / W2 / W3 closure."""
import io, json, os, random, zipfile
import pytest
from cutwitness import w1, w2, w3
from cutwitness.model import history_digest, legal_state, prefix_legal, src
from cutwitness.oracles import duckdb_obs, obs_digest, reference_obs
from cutwitness.targetsql import ddl, postprocess, target_sql
from cutwitness.w1fixtures import history as fixture_history

TOKEN = "cw-test-refresh-token-0123456789abcdef"


class FakeHTTP:
    """Mock opener for the Mobility Database API (records every request; returns canned JSON / zip bytes)."""

    def __init__(self, feeds, datasets, blobs):
        self.feeds, self.datasets, self.blobs, self.requests = feeds, datasets, blobs, []

    def __call__(self, req, timeout=None):
        self.requests.append((req.full_url, dict(req.header_items()), req.data))
        u = req.full_url
        if u.endswith("/v1/tokens"):
            body = {"access_token": "ACCESS-123"}
        elif "/datasets" in u:
            body = self.datasets
        elif "/v1/gtfs_feeds/" in u:
            body = {"id": "F1", "source_info": {"license_url": "https://creativecommons.org/licenses/by/4.0/"}}
        elif u in self.blobs:
            return io.BytesIO(self.blobs[u])
        else:
            body = self.feeds
        return io.BytesIO(json.dumps(body).encode())


def _fake():
    fx = fixture_history()
    ds = [{"id": f"d{i}", "downloaded_at": t, "hosted_url": f"https://files.example/d{i}.zip"} for i, (t, _) in enumerate(fx)]
    return FakeHTTP([], ds, {f"https://files.example/d{i}.zip": b for i, (_, b) in enumerate(fx)})


def test_w1_token_only_from_environment_and_never_persisted(monkeypatch, tmp_path):
    monkeypatch.delenv("CUTWITNESS_W1_TOKEN", raising=False)
    c = w1.CatalogClient(opener=_fake())
    with pytest.raises(PermissionError):
        c.get("/v1/gtfs_feeds")
    monkeypatch.setenv("CUTWITNESS_W1_TOKEN", TOKEN)
    http = _fake(); c = w1.CatalogClient(opener=http)
    fw = w1.SplitFirewall(["F1"], []); man = w1.materialize_feed(c, "F1", fw, 20, "seed", 60, str(tmp_path))
    blob = json.dumps(man) + repr(c.__dict__)
    assert TOKEN not in blob and "ACCESS-123" not in json.dumps(man)
    sent = [r for r in http.requests if r[2] and TOKEN.encode() in r[2]]
    assert len(sent) == 1 and sent[0][0].endswith("/v1/tokens")          # token only ever sent to the token endpoint
    for d, _, fs in os.walk(tmp_path):
        for f in fs:
            assert TOKEN.encode() not in open(os.path.join(d, f), "rb").read()


def test_w1_frozen_selection_rule_and_firewall():
    feeds = [{"id": f"mdb-{i}", "status": "active", "n_datasets": 12 + (i % 3)} for i in range(40)] + \
            [{"id": "small", "status": "active", "n_datasets": 11}, {"id": "dead", "status": "inactive", "n_datasets": 50}]
    v1, t1 = w1.select_regions(feeds, "seed-A"); v2, t2 = w1.select_regions(list(reversed(feeds)), "seed-A")
    assert (v1, t1) == (v2, t2) and len(v1) == 8 and len(t1) == 16 and not set(v1) & set(t1)
    assert "small" not in v1 + t1 and "dead" not in v1 + t1
    assert w1.select_regions(feeds, "seed-B") != (v1, t1)
    with pytest.raises(RuntimeError):
        w1.select_regions(feeds[:10], "seed-A")
    fw = w1.SplitFirewall(v1, t1)
    fw.check(v1[0])
    with pytest.raises(PermissionError):
        fw.check(t1[0])
    with pytest.raises(PermissionError):
        fw.check("outside")
    fw.open_test(); fw.check(t1[0])
    with pytest.raises(ValueError):
        w1.SplitFirewall(["a"], ["a"])


def test_w1_licence_classes():
    assert w1.license_class({"source_info": {"license_url": "https://creativecommons.org/licenses/by/4.0/"}}) == "REDISTRIBUTABLE"
    assert w1.license_class({"source_info": {"license_url": "https://agency.example/terms-license"}}) == "DERIVED_ONLY"
    assert w1.license_class({}) == "NO_REDISTRIBUTION"


def test_w1_golden_history_versions_recurrence_and_legal_diffs():
    s = w1.schema()
    snaps = [(t, w1.normalize(b, 20, "seed")) for t, b in fixture_history()]
    vs = w1.logical_versions(snaps)
    assert len(snaps) == 9 and len(vs) == 8                    # identical consecutive snapshot collapsed
    assert vs[2]["recurrence_of"] == 0 and vs[3]["recurrence_of"] == 1   # revert to v0, reapply v1
    txns = w1.diff_transactions(s, vs)
    assert prefix_legal(s, txns)[0]
    deltas = [{t: z.d for t, z in x.delta.items()} for x in txns]
    mass = [d for d in deltas if "stop_times" in d and sum(1 for m in d["stop_times"].values() if m < 0) >= 6]
    assert mass, "mass delete/reinsert transition present"
    assert any("calendar_dates" in d for d in deltas)
    fk_remove = [d for d in deltas if any(m < 0 for m in d.get("routes", {}).values())]
    fk_add = [d for d in deltas if any(m > 0 for m in d.get("routes", {}).values()) and any(m > 0 for m in d.get("stops", {}).values())]
    assert fk_remove and fk_add


def test_w1_views_reference_equals_duckdb():
    s = w1.schema(); vs = w1.views(s)
    txns = w1.diff_transactions(s, w1.logical_versions([(t, w1.normalize(b, 20, "seed")) for t, b in fixture_history()]))
    for k in range(1, len(txns) + 1):
        x = src(s, txns[:k])
        assert obs_digest(reference_obs(vs, x)) == obs_digest(duckdb_obs(s, vs, x))


def test_w2_six_views_reference_duckdb_and_flat_target_sql():
    import duckdb
    s = w2.schema(); h = w2.refresh_stream(random.Random(3), s, 3); vs = w2.views(s)
    assert len(vs) == 6 and "NOT byte-identical" in w2.W2_METADATA["shape"] and "SUM(l_extendedprice)" in w2.W2_METADATA["revenue_measure"]
    assert prefix_legal(s, h)[0]
    x = src(s, h); ref = reference_obs(vs, x)
    assert obs_digest(ref) == obs_digest(duckdb_obs(s, vs, x))
    con = duckdb.connect()
    for st in ddl(s, "duckdb"):
        con.execute(st)
    for t in s.order:
        for r, m in x[t].items_sorted():
            con.execute(f"INSERT INTO {t} VALUES ({', '.join('?' for _ in r)})", list(r))
    for v in vs:
        q, n = target_sql(v, s, "duckdb")
        assert postprocess(v, s, n, con.execute(q).fetchall()).digest() == ref[v.name].digest(), v.name


@pytest.mark.parametrize("seed", range(25))
def test_w3_legal_deterministic_supported_and_cross_checked(seed):
    a = random.Random(seed); b = random.Random(seed)
    s1 = w3.gen_schema(a); v1 = w3.gen_views(a, s1); h1 = w3.gen_history(a, s1, 8)
    s2 = w3.gen_schema(b); v2 = w3.gen_views(b, s2); h2 = w3.gen_history(b, s2, 8)
    assert history_digest(h1) == history_digest(h2) and [v.digest() for v in v1] == [v.digest() for v in v2]
    assert prefix_legal(s1, h1)[0]
    for v in v1:
        assert {op.kind for op in v.ops} <= {"group", "distinct", "topk", "join", "leftjoin"} and len(v.ops) <= 2
    assert obs_digest(reference_obs(v1, src(s1, h1))) == obs_digest(duckdb_obs(s1, v1, src(s1, h1)))
