from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.auth.policy import DeclarativePolicy


def test_generic_policy_preserves_format_and_requires_aware_time() -> None:
    policy = DeclarativePolicy(timezone="Pacific/Auckland", template="%Y-%j")
    assert policy.verify("2032-002", datetime(2032, 1, 1, 23, tzinfo=UTC))
    assert not policy.verify("2032-001", datetime(2032, 1, 1, 23, tzinfo=UTC))
    assert not policy.verify("０", datetime(2032, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="timezone-aware"):
        policy.verify("2032-001", datetime(2032, 1, 1))


def test_policy_rejects_executable_or_unbounded_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        DeclarativePolicy(timezone="UTC", template="%c")
    with pytest.raises(ValidationError):
        DeclarativePolicy.model_validate(
            {"timezone": "UTC", "template": "%Y", "execute": "anything"}
        )
    path = tmp_path / "fixture.json"
    path.write_text(" " * 2049)
    with pytest.raises(ValueError, match="size limit"):
        DeclarativePolicy.load(path)
