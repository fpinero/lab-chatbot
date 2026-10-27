import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("dev_server", ROOT / "scripts/dev-server.py")
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


@pytest.mark.parametrize("signature", [None, "", "old-process"])
def test_stop_never_signals_unverified_or_reused_pid(monkeypatch, signature):
    monkeypatch.setattr(dev, "process_signature", lambda pid: "current-process")
    signals = []
    monkeypatch.setattr(dev.os, "killpg", lambda *args: signals.append(args))
    assert not dev.stop_process({"pid": 12345, "signature": signature})
    assert not signals


def test_dead_pid_without_signature_is_not_owned(monkeypatch):
    monkeypatch.setattr(dev, "process_signature", lambda pid: None)
    assert not dev.owns_process({"pid": 12345})


def test_stop_refuses_changed_process_group(monkeypatch):
    monkeypatch.setattr(dev, "process_signature", lambda pid: "matching-process")
    monkeypatch.setattr(dev.os, "getpgid", lambda pid: pid + 1)
    with pytest.raises(dev.DevError, match="process group changed"):
        dev.stop_process({"pid": 12345, "signature": "matching-process"})


def test_other_checkout_state_is_never_used(tmp_path):
    (tmp_path / "state.json").write_text(json.dumps({"root": "/another/checkout", "processes": []}))
    with pytest.raises(dev.DevError, match="another checkout"):
        dev.load_state(tmp_path)


def test_parallel_start_stop_operations_are_excluded(tmp_path):
    with dev.state_lock(tmp_path):
        with pytest.raises(dev.DevError, match="operation is in progress"):
            with dev.state_lock(tmp_path):
                pytest.fail("A concurrent operation acquired the same lock")


def test_unmanaged_listener_prevents_start_without_signals(monkeypatch, tmp_path):
    monkeypatch.setattr(dev, "port_busy", lambda port: True)
    signals = []
    monkeypatch.setattr(dev.os, "killpg", lambda *args: signals.append(args))
    args = SimpleNamespace(backend_port=28100, frontend_port=25174)
    with pytest.raises(dev.DevError, match="unmanaged process"):
        dev.start(args, tmp_path)
    assert not signals
    assert not (tmp_path / "state.json").exists()


def test_frontend_environment_excludes_backend_and_vite_credentials(monkeypatch):
    for key in ["OPENROUTER_API_KEY", "AUTH_PASSWORD_HASH", "ACCESS_OWNER_SUBJECT", "VITE_KEY"]:
        monkeypatch.setenv(key, "synthetic-private-value")
    environment = dev.frontend_environment(Path("/example/bin/node"), 28100)
    assert "synthetic-private-value" not in environment.values()
    assert environment["LAB_BROWSER_API_PORT"] == "28100"
    assert environment["PATH"].startswith("/example/bin:")


@pytest.fixture
def local_environment(tmp_path, password_hash, monkeypatch):
    from app.config import Settings

    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    owner = tmp_path / "owner.hash"
    owner.write_text(password_hash.get_secret_value())
    filename = tmp_path / ".env"
    filename.write_text(
        f"AUTH_PASSWORD_HASH_FILE={owner}\nPROVIDER_MODE=mock\n"
        'MODEL_ALLOWLIST=["synthetic/model"]\n'
        "OPENROUTER_API_KEY=synthetic-$KEY-$(touch marker)\n"
    )
    return filename


def test_environment_is_data_and_origin_tracks_frontend_port(local_environment):
    environment, mode = dev.backend_environment(local_environment, 25174)
    assert mode == "mock"
    assert environment["APP_ORIGIN"] == "http://127.0.0.1:25174"
    assert environment["OPENROUTER_API_KEY"] == "synthetic-$KEY-$(touch marker)"


def test_production_configuration_is_refused(local_environment):
    with local_environment.open("a") as handle:
        handle.write("APP_ENV=production\n")
    with pytest.raises(dev.DevError, match="refuse production"):
        dev.backend_environment(local_environment, 25174)


def test_invalid_environment_never_echoes_private_values(local_environment):
    with local_environment.open("a") as handle:
        handle.write("MODEL_ALLOWLIST=synthetic-private-invalid-value\n")
    with pytest.raises(dev.DevError, match="configuration is invalid") as error:
        dev.backend_environment(local_environment, 25174)
    assert "synthetic-private" not in str(error.value)
