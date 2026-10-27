import runpy
import sys
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "live-text.py"


def test_live_plan_cannot_open_a_network_client(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Read-only planning must not create an HTTP client")

    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setenv("LIVE_TEST_BUDGET_USD", "0.001")
    monkeypatch.setattr(
        sys, "argv", [str(SCRIPT), "--model", "synthetic/model", "--max-usd", "0.001"]
    )
    runpy.run_path(str(SCRIPT), run_name="__main__")
    assert "Plan:" in capsys.readouterr().out


def test_live_execution_requires_an_approved_numeric_allowance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVE_TEST_BUDGET_USD", raising=False)
    monkeypatch.setattr(
        sys, "argv", [str(SCRIPT), "--model", "synthetic/model", "--max-usd", "0.001", "--execute"]
    )
    with pytest.raises(SystemExit, match="approved"):
        runpy.run_path(str(SCRIPT), run_name="__main__")


def test_live_image_plan_and_budget_gate_never_open_network(monkeypatch, capsys) -> None:
    script = SCRIPT.with_name("live-image.py")

    def forbidden(*args, **kwargs):
        raise AssertionError("Planning and rejected execution must not create an HTTP client")

    monkeypatch.setattr(httpx, "Client", forbidden)
    arguments = [
        str(script),
        "--model",
        "synthetic/image",
        "--provider",
        "synthetic",
        "--max-usd",
        "0.001",
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    monkeypatch.setenv("LIVE_TEST_BUDGET_USD", "0.001")
    runpy.run_path(str(script), run_name="__main__")
    assert "Plan:" in capsys.readouterr().out
    monkeypatch.delenv("LIVE_TEST_BUDGET_USD", raising=False)
    monkeypatch.setattr(sys, "argv", [*arguments, "--execute"])
    with pytest.raises(SystemExit, match="approved"):
        runpy.run_path(str(script), run_name="__main__")


@pytest.mark.parametrize("name", ["live-text.py", "live-image.py"])
def test_provider_budget_plans_need_no_local_amount_or_network(monkeypatch, capsys, name):
    def forbidden(*args, **kwargs):
        raise AssertionError("Planning must remain network-free")

    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setenv("SPEND_CONTROL", "provider")
    monkeypatch.delenv("LIVE_TEST_BUDGET_USD", raising=False)
    script = SCRIPT.with_name(name)
    arguments = [str(script), "--model", "synthetic/model"]
    if name == "live-image.py":
        arguments += ["--provider", "synthetic"]
    monkeypatch.setattr(sys, "argv", arguments)
    runpy.run_path(str(script), run_name="__main__")
    assert "Plan:" in capsys.readouterr().out
