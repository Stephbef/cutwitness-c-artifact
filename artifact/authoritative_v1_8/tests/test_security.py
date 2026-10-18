"""Secrets/privacy scanning of the source tree and positive controls."""
import os
from cutwitness.security import dockerfile_findings, scan

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_source_tree_has_no_secrets_or_private_paths():
    f = [x for x in scan(ROOT) if not x["file"].startswith(("runs/", "qa/"))]
    assert f == [], f


def test_positive_controls_are_detected(tmp_path):
    (tmp_path / ".env").write_text("A=1")
    (tmp_path / "k.txt").write_text("-----BEGIN RSA PRIVATE KEY-----\nabc")
    (tmp_path / "j.txt").write_text("Bearer abcdefghijklmnopqrstuvwxyz0123")
    (tmp_path / "p.txt").write_text("see /home/alice/secret")
    (tmp_path / "t.txt").write_text("value cw-token-value-123")
    kinds = {x["kind"] for x in scan(str(tmp_path), extra_secrets=["cw-token-value-123"])}
    assert {"forbidden_file", "private_key", "bearer_value", "private_path", "configured_secret_value"} <= kinds


def test_dockerfiles_carry_no_secret_layers(tmp_path):
    assert dockerfile_findings(os.path.join(ROOT, "server")) == []
    (tmp_path / "Dockerfile").write_text("FROM x\nENV API_TOKEN=abc\n")
    assert dockerfile_findings(str(tmp_path))


def test_offline_hash_checked_install_contract():
    lock = open(os.path.join(ROOT, "vendor", "requirements.lock")).read()
    wheels = [w for w in os.listdir(os.path.join(ROOT, "vendor", "wheels")) if w.endswith(".whl")]
    for line in [l for l in lock.splitlines() if l and not l.startswith("#")]:
        assert "--hash=sha256:" in line
    sh = open(os.path.join(ROOT, "run_one_shot.sh")).read()
    assert "--no-index" in sh and "--require-hashes" in sh and "pip download" not in sh and "pypi.org" not in sh
    assert wheels
