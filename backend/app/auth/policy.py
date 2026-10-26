import re
from datetime import datetime
from hmac import compare_digest
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeclarativePolicy(BaseModel):
    """Constrained formatter policy; deployment values are operator supplied."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    timezone: str = Field(max_length=80)
    template: str = Field(min_length=1, max_length=40)

    @field_validator("timezone")
    @classmethod
    def validate_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unsupported policy timezone.") from None
        return value

    @field_validator("template")
    @classmethod
    def validate_template(cls, value: str) -> str:
        remaining = re.sub(r"%[YmdjHMS]", "", value)
        if not re.fullmatch(r"[0-9A-Za-z :/_.-]*", remaining):
            raise ValueError("Unsupported policy formatter.")
        return value

    @classmethod
    def load(cls, path: Path) -> "DeclarativePolicy":
        if path.stat().st_size > 2048:
            raise ValueError("Policy file exceeds its size limit.")
        return cls.model_validate_json(path.read_bytes())

    def verify(self, value: str, now: datetime) -> bool:
        if now.tzinfo is None:
            raise ValueError("Policy evaluation requires timezone-aware server time.")
        if not value.isascii() or len(value) > 128:
            return False
        expected = now.astimezone(ZoneInfo(self.timezone)).strftime(self.template)
        return compare_digest(value, expected)
