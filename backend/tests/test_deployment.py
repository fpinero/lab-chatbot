import copy
import importlib.util
import io
import json
import os
import sqlite3
import sys
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from cryptography.exceptions import InvalidTag

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), ROOT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release = load_script("release")
backup = load_script("backup-data")


@pytest.fixture
def config(tmp_path, password_hash):
    key = tmp_path / "provider.key"
    owner = tmp_path / "owner.hash"
    key.write_text("synthetic-deployment-key-never-print")
    owner.write_text(password_hash.get_secret_value())
    key.chmod(0o600)
    owner.chmod(0o600)
    return release.Config(
        "synthetic-context",
        "labchatbot",
        "labchatbot",
        "app",
        "registry.invalid:5000/team/labchatbot",
        "linux/arm64",
        "https://labchatbot.invalid",
        "kubectl",
        "kubeconform",
        key,
        owner,
    )


@pytest.mark.parametrize(
    "image,tag",
    [
        ("registry.invalid:5000/team/labchatbot:41", "41"),
        ("registry.invalid:5000/team/labchatbot:v9", "v9"),
        ("registry.invalid:5000/team/labchatbot:3@sha256:" + "a" * 64, "3"),
    ],
)
def test_production_tag_parsing_preserves_registry_ports(config, image, tag):
    assert release.image_tag(image, config.repository) == tag


@pytest.mark.parametrize("suffix", [":latest", ":0.1.0", ":01", "@sha256:" + "a" * 64, ":../bad"])
def test_ambiguous_production_tags_are_rejected(config, suffix):
    with pytest.raises(release.ReleaseError):
        release.image_tag(config.repository + suffix, config.repository)


def deployment(config, version="1", image=None):
    return {
        "metadata": {"resourceVersion": version},
        "spec": {
            "template": {
                "spec": {
                    "containers": [{"name": "app", "image": image or config.repository + ":41"}]
                }
            }
        },
    }


def test_only_confirmed_notfound_allows_first_release(config, monkeypatch):
    monkeypatch.setattr(release.Config, "get", lambda *args: None)
    assert release.baseline(config)["next_tag"] == "1"
    for category in ["forbidden", "unavailable", "timed out"]:

        def failed(*args, category=category):
            raise release.ToolError(category)

        monkeypatch.setattr(release.Config, "get", failed)
        with pytest.raises(release.ToolError):
            release.baseline(config)


def test_live_production_and_resource_version_drive_the_plan(config, monkeypatch):
    current = deployment(config)
    monkeypatch.setattr(release.Config, "get", lambda *args: copy.deepcopy(current))
    plan = release.baseline(config)
    assert plan["next_tag"] == "42"
    release.ensure_baseline(config, plan)
    current["metadata"]["resourceVersion"] = "2"
    with pytest.raises(release.ReleaseError, match="Production changed"):
        release.ensure_baseline(config, plan)


@pytest.mark.parametrize(
    "message",
    [
        "unauthorized",
        "denied",
        "connection timed out",
        "docker-credential-helper: executable file not found",
        "registry.invalid:5000/team/labchatbot:1: not found unauthorized",
    ],
)
def test_registry_errors_are_never_treated_as_an_unused_tag(config, monkeypatch, message):
    monkeypatch.setattr(
        release, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr=message)
    )
    with pytest.raises(release.ReleaseError, match="Registry existence"):
        release.registry(config.repository + ":1")


@pytest.mark.parametrize(
    "message",
    ["manifest unknown", "no such manifest", "registry.invalid:5000/team/labchatbot:1: not found"],
)
def test_registry_confirmed_absence_is_distinct(config, monkeypatch, message):
    monkeypatch.setattr(
        release, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr=message)
    )
    assert release.registry(config.repository + ":1") is None


def test_existing_tag_requires_matching_source_and_digest(config, tmp_path, monkeypatch):
    monkeypatch.setattr(release, "verify_remote", lambda *args: None)
    monkeypatch.setattr(release, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(release, "fingerprint", lambda: "current-source")
    monkeypatch.setattr(release, "registry", lambda image: {"digest": "sha256:" + "a" * 64})
    lock = SimpleNamespace(check=lambda: None)
    plan = {"next_tag": "1"}
    with pytest.raises(release.ReleaseError, match="already exists"):
        release.publish(config, plan, lock)
    path = release.receipt_path(config, "1")
    release.write_record(path, {"fingerprint": "current-source", "digest": "sha256:" + "a" * 64})
    assert release.publish(config, plan, lock)["fingerprint"] == "current-source"
    release.write_record(path, {"fingerprint": "other-source", "digest": "sha256:" + "a" * 64})
    with pytest.raises(release.ReleaseError, match="already exists"):
        release.publish(config, plan, lock)


def test_distributed_lock_excludes_another_machine_and_preserves_new_owner(config, monkeypatch):
    stored = [None]

    def get(*args):
        return copy.deepcopy(stored[0])

    def kube(self, *args, **kwargs):
        value = json.loads(kwargs["data"])
        previous = stored[0]
        if (
            previous
            and value["metadata"].get("resourceVersion") != previous["metadata"]["resourceVersion"]
        ):
            raise release.ToolError("conflict")
        value["metadata"]["resourceVersion"] = (
            str(int(previous["metadata"]["resourceVersion"]) + 1) if previous else "1"
        )
        stored[0] = value

    monkeypatch.setattr(release.Config, "get", get)
    monkeypatch.setattr(release.Config, "kube", kube)
    with release.Lease(config) as first:
        assert stored[0]["spec"]["holderIdentity"] == first.holder
        with pytest.raises(release.ReleaseError, match="Another machine"):
            with release.Lease(config):
                raise AssertionError("Second lock entered")
        first.lost.set()
        with pytest.raises(release.ReleaseError, match="lock was lost"):
            first.check()
        stored[0]["spec"]["holderIdentity"] = "other-owner"
    assert stored[0]["spec"]["holderIdentity"] == "other-owner"
    stored[0]["spec"]["renewTime"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    with release.Lease(config):
        assert stored[0]["spec"]["holderIdentity"] != "other-owner"
    assert stored[0]["spec"]["holderIdentity"] == ""


@pytest.mark.parametrize(
    "command", ["plan", "publish", "deploy", "release", "rollback", "bootstrap", "secrets"]
)
def test_every_write_phase_defaults_to_a_non_mutating_plan(config, monkeypatch, capsys, command):
    monkeypatch.setattr(release.Config, "load", lambda path: config)
    monkeypatch.setattr(release.Config, "get", lambda *args: None)
    monkeypatch.setattr(release, "fingerprint", lambda: "fixture-fingerprint")

    def forbidden(*args, **kwargs):
        raise AssertionError("A default plan must never invoke a mutation tool")

    monkeypatch.setattr(release, "run", forbidden)
    monkeypatch.setattr(sys, "argv", ["release.py", command])
    release.main()
    output = capsys.readouterr().out
    assert json.loads(output)["executed"] is False
    assert "synthetic-deployment-key-never-print" not in output
    assert config.hash_file.read_text() not in output


def test_local_gate_rejects_unready_or_modified_source(config, tmp_path, monkeypatch):
    with pytest.raises(release.ReleaseError, match="RELEASE_READY"):
        release.local_gate(config)
    ready = release.Config(**{**config.__dict__, "release_ready": True})
    monkeypatch.setattr(release, "run", lambda *args, **kwargs: SimpleNamespace(stdout="dirty"))
    with pytest.raises(release.ReleaseError, match="Commit"):
        release.local_gate(ready)
    responses = iter(["", "main"])
    monkeypatch.setattr(
        release, "run", lambda *args, **kwargs: SimpleNamespace(stdout=next(responses))
    )
    monkeypatch.setattr(release, "ARTIFACTS", tmp_path)
    with pytest.raises(release.ReleaseError, match="exact source tree"):
        release.local_gate(ready)


def test_kubernetes_client_version_gate(config, monkeypatch):
    def kube(self, *args, **kwargs):
        return SimpleNamespace(
            stdout=json.dumps(
                {
                    "clientVersion": {"gitVersion": "v1.36.1"},
                    "serverVersion": {"gitVersion": "v1.25.6+k3s1"},
                }
            )
        )

    monkeypatch.setattr(release.Config, "kube", kube)
    with pytest.raises(release.ReleaseError, match="one minor version"):
        release.compatible_client(config)


def test_remote_image_source_and_architecture_must_match_receipt(config, monkeypatch):
    saved = {
        "image": config.repository + ":1",
        "digest": "sha256:" + "a" * 64,
        "fingerprint": "verified",
    }
    raw = {
        "os": "linux",
        "architecture": "arm64",
        "config": {"Labels": {"com.labchatbot.source-fingerprint": "verified"}},
    }
    monkeypatch.setattr(
        release, "run", lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(raw))
    )
    release.verify_remote(config, saved)
    raw["architecture"] = "amd64"
    with pytest.raises(release.ReleaseError, match="architecture"):
        release.verify_remote(config, saved)
    raw["architecture"] = "arm64"
    raw["config"]["Labels"]["com.labchatbot.source-fingerprint"] = "different"
    with pytest.raises(release.ReleaseError, match="recorded source"):
        release.verify_remote(config, saved)


@pytest.mark.parametrize("conflict", [False, True])
def test_deployment_uses_one_cas_write_without_reapplying_infrastructure(
    config, monkeypatch, tmp_path, conflict
):
    ready = release.Config(**{**config.__dict__, "origin_verified": True})
    old = {
        "image": config.repository + ":41",
        "resource_version": "5",
        "spec_hash": "baseline",
        "next_tag": "42",
    }
    current = copy.deepcopy(old)
    saved = {
        "image": config.repository + ":42",
        "tag": "42",
        "digest": "sha256:" + "a" * 64,
        "fingerprint": "verified",
        "platform": config.platform,
        "baseline": old,
    }
    source = yaml.safe_load((ROOT / "k8s/deployment.yaml").read_text())
    source["spec"]["template"]["spec"]["containers"][0]["image"] = (
        saved["image"] + "@" + saved["digest"]
    )
    commands = []

    def kube(self, *args, **kwargs):
        commands.append(args)
        if args[0] == "replace":
            value = json.loads(kwargs["data"])
            assert value["metadata"]["resourceVersion"] == "5"
            if conflict:
                raise release.ToolError("conflict")
            current["image"] = value["spec"]["template"]["spec"]["containers"][0]["image"]
        return SimpleNamespace(
            stdout="labchatbot-secrets", returncode=1 if args[0] == "diff" else 0
        )

    monkeypatch.setattr(release.Config, "kube", kube)
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "ARTIFACTS", tmp_path / "artifacts")
    monkeypatch.setattr(release, "fingerprint", lambda: "verified")
    monkeypatch.setattr(release, "registry", lambda *args: {"digest": saved["digest"]})
    monkeypatch.setattr(release, "verify_remote", lambda *args: None)
    monkeypatch.setattr(release, "health_check", lambda *args: None)
    monkeypatch.setattr(release, "baseline", lambda *args: copy.deepcopy(current))
    monkeypatch.setattr(release, "render", lambda *args: [copy.deepcopy(source)])
    monkeypatch.setattr(release, "validate", lambda *args, **kwargs: None)
    lock = SimpleNamespace(check=lambda: None)
    if conflict:
        with pytest.raises(release.ToolError, match="conflict"):
            release.deploy(ready, old, saved, False, lock)
        assert not (tmp_path / "k8s/release-state.local.json").exists()
    else:
        release.deploy(ready, old, saved, False, lock)
        assert (tmp_path / "k8s/release-state.local.json").is_file()
    assert sum(command[0] == "replace" for command in commands) == 1
    assert not any(command[0] in {"apply", "delete", "create"} for command in commands)


def test_changed_publication_baseline_aborts_before_tools(config, monkeypatch):
    ready = release.Config(**{**config.__dict__, "origin_verified": True})
    monkeypatch.setattr(release, "fingerprint", lambda: "verified")

    def forbidden(*args, **kwargs):
        raise AssertionError("Stale publication must not reach tools")

    monkeypatch.setattr(release, "registry", forbidden)
    with pytest.raises(release.ReleaseError, match="Production changed after publication"):
        release.deploy(
            ready,
            {"resource_version": "new"},
            {"fingerprint": "verified", "baseline": {"resource_version": "old"}},
            False,
            None,
        )


def test_manifest_topology_and_privacy_contract():
    resources = {
        item["kind"]: item
        for item in [
            yaml.safe_load((ROOT / "k8s" / name).read_text())
            for name in yaml.safe_load((ROOT / "k8s/kustomization.yaml").read_text())["resources"]
        ]
    }
    assert set(resources) == release.KINDS
    assert "Secret" not in resources
    spec = resources["Deployment"]["spec"]
    assert spec["replicas"] == 1 and spec["strategy"]["type"] == "Recreate"
    pod = spec["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    container = pod["containers"][0]
    assert container["name"] == "app" and container["securityContext"]["readOnlyRootFilesystem"]
    assert resources["Service"]["spec"]["type"] == "ClusterIP"
    assert resources["ConfigMap"]["data"]["SPEND_CONTROL"] == "provider"
    assert resources["Ingress"]["spec"]["ingressClassName"] == "traefik"
    assert "tls" not in resources["Ingress"]["spec"]
    assert not any("cert-manager" in str(item) for item in resources.values())


def test_diff_summary_never_returns_live_inline_credentials(config, monkeypatch):
    current = {"data": {"OPENROUTER_API_KEY": "synthetic-secret-never-return"}}
    desired = [
        {
            "kind": "ConfigMap",
            "metadata": {"name": "labchatbot-config"},
            "data": {"SPEND_CONTROL": "provider"},
        }
    ]
    monkeypatch.setattr(release, "validate", lambda *args, **kwargs: None)
    monkeypatch.setattr(release.Config, "get", lambda *args: current)
    monkeypatch.setattr(
        release.Config, "kube", lambda *args, **kwargs: SimpleNamespace(returncode=1)
    )
    result = release.diff_summary(config, desired)
    assert result["changes"] and result["values_redacted"]
    assert "synthetic-secret-never-return" not in json.dumps(result)
    assert "/data/OPENROUTER_API_KEY" in result["resources"][0]["changed_field_paths"]


def make_data(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    with sqlite3.connect(data / "lab.db") as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE fixture (value TEXT)")
        db.execute("INSERT INTO fixture VALUES ('synthetic history')")
    (data / "media").mkdir()
    (data / "media/image.webp").write_bytes(b"synthetic-private-image")
    return data


def test_encrypted_backup_restores_sqlite_and_assets_without_overwrite(tmp_path):
    data = make_data(tmp_path)
    archive = tmp_path / "snapshot.enc"
    key = os.urandom(32)
    with pytest.raises(ValueError, match="offline"):
        backup.backup(data, archive, key, False)
    result = backup.backup(data, archive, key, True)
    assert result["encrypted"] and b"synthetic history" not in archive.read_bytes()
    target = tmp_path / "restored"
    assert backup.restore(archive, target, key)["overwrote_existing_data"] is False
    with sqlite3.connect(target / "lab.db") as db:
        assert db.execute("SELECT value FROM fixture").fetchone()[0] == "synthetic history"
    assert (target / "media/image.webp").read_bytes() == b"synthetic-private-image"
    with pytest.raises(ValueError, match="new directory"):
        backup.restore(archive, target, key)
    with pytest.raises(ValueError, match="never overwrite"):
        backup.backup(data, archive, key, True)
    second = tmp_path / "second.enc"
    backup.backup(target, second, key, True)
    backup.restore(second, tmp_path / "second-restore", key)


def test_tampered_backup_is_rejected_before_extraction(tmp_path):
    data = make_data(tmp_path)
    archive = tmp_path / "snapshot.enc"
    key = os.urandom(32)
    backup.backup(data, archive, key, True)
    payload = bytearray(archive.read_bytes())
    payload[len(backup.MAGIC) + 20] ^= 1
    archive.write_bytes(payload)
    with pytest.raises(InvalidTag):
        backup.restore(archive, tmp_path / "restored", key)
    assert not (tmp_path / "restored").exists()
    assert (data / "media/image.webp").exists()


def test_authenticated_but_unsafe_archive_never_escapes_restore_directory(tmp_path):
    key = os.urandom(32)
    plain = tmp_path / "unsafe.tar.gz"
    with tarfile.open(plain, "w:gz") as archive:
        member = tarfile.TarInfo("data/../../escaped")
        member.size = 4
        archive.addfile(member, io.BytesIO(b"test"))
    encrypted = tmp_path / "unsafe.enc"
    backup.encrypt(plain, encrypted, key)
    with pytest.raises(ValueError, match="Unsafe"):
        backup.restore(encrypted, tmp_path / "restored", key)
    assert not (tmp_path / "escaped").exists()
    assert not (tmp_path / "restored").exists()


def test_backup_destination_cannot_alias_the_live_data_directory(tmp_path):
    data = make_data(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(data, target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        backup.backup(data, alias / "snapshot.enc", os.urandom(32), True)
    assert not (data / "snapshot.enc").exists()
