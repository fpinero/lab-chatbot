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
