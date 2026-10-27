import asyncio
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.service import AuthError
from app.config import Settings
from app.models import CatalogCache
from app.providers.chat import ChatProvider, ProviderError


class ModelInfo(BaseModel):
    id: str
    name: str
    api_family: Literal["chat"] = "chat"
    input_modalities: list[str]
    output_modalities: list[str]
    supported_parameters: list[str]
    context_length: int = Field(gt=0)
    max_completion_tokens: int | None = None
    pricing: dict[str, str]
    simulated: bool


class CatalogInfo(BaseModel):
    models: list[ModelInfo]
    fetched_at: int
    stale: bool
    ranking: str


class CatalogService:
    def __init__(
        self, engine: Engine, settings: Settings, provider: ChatProvider, now: Callable[[], int]
    ) -> None:
        self.engine, self.settings, self.provider, self.now = engine, settings, provider, now
        self.lock = asyncio.Lock()

    def normalize(self, values: list[dict[str, Any]]) -> list[ModelInfo]:
        models = []
        for raw in values:
            try:
                if not isinstance(raw, dict):
                    continue
                architecture = raw.get("architecture") or {}
                prices = raw.get("pricing") or {}
                if not isinstance(architecture, dict) or not isinstance(prices, dict):
                    continue
                if any(
                    not Decimal(str(price)).is_finite() or Decimal(str(price)) < 0
                    for price in prices.values()
                ):
                    continue
                model = ModelInfo(
                    id=raw["id"],
                    name=raw["name"],
                    input_modalities=architecture.get("input_modalities", []),
                    output_modalities=architecture.get("output_modalities", []),
                    supported_parameters=raw.get("supported_parameters") or [],
                    context_length=raw.get("context_length"),
                    max_completion_tokens=(raw.get("top_provider") or {}).get(
                        "max_completion_tokens"
                    ),
                    pricing={str(key): str(value) for key, value in prices.items()},
                    simulated=self.settings.provider_mode == "mock",
                )
                if "text" not in model.input_modalities or "text" not in model.output_modalities:
                    continue
                if self.settings.model_allowlist and model.id not in self.settings.model_allowlist:
                    continue
                ceiling = self.settings.model_price_ceiling_per_million / 1_000_000
                if self.settings.spend_control == "application" and any(
                    Decimal(model.pricing.get(key, "Infinity")) > ceiling
                    for key in ["prompt", "completion"]
                ):
                    continue
                models.append(model)
            except (
                ValidationError,
                ValueError,
                KeyError,
                TypeError,
                ArithmeticError,
                AttributeError,
            ):
                continue
        return models

    async def get(self, refresh: bool = False) -> CatalogInfo:
        if (
            self.settings.provider_mode == "openrouter"
            and not self.settings.openrouter_api_key.get_secret_value()
        ):
            raise AuthError(
                503, "provider_unconfigured", "Configure a restricted provider key first."
            )
        async with self.lock:
            now = self.now()
            family = "chat:provider" if self.settings.spend_control == "provider" else "chat"
            with Session(self.engine) as db:
                cached = db.get(CatalogCache, family)
                if not cached:
                    cached = CatalogCache(
                        family=family, catalog_json="[]", fetched_at=0, last_attempt_at=0
                    )
                    db.add(cached)
                    db.commit()
                    db.refresh(cached)
                data, fetched, attempt = (
                    cached.catalog_json,
                    cached.fetched_at,
                    cached.last_attempt_at,
                )
                due = now - fetched >= 900 or not fetched
                if refresh and attempt and now - attempt < 60:
                    raise AuthError(
                        429, "catalog_throttled", "Wait before refreshing the catalog again."
                    )
                should_fetch = refresh or (due and now - attempt >= 60)
                if should_fetch:
                    cached.last_attempt_at = now
                    db.commit()
            if should_fetch:
                try:
                    normalized = self.normalize(await self.provider.catalog())
                    if not normalized:
                        raise ProviderError("catalog_invalid")
                    data = json.dumps([model.model_dump() for model in normalized])
                    fetched = now
                    with Session(self.engine) as db:
                        row = db.get(CatalogCache, family)
                        if row:
                            row.catalog_json, row.fetched_at = data, fetched
                            db.commit()
                except ProviderError:
                    if not fetched:
                        raise AuthError(
                            503, "catalog_unavailable", "Model catalog is unavailable. Try later."
                        ) from None
            if not fetched:
                raise AuthError(
                    503, "catalog_unavailable", "Model catalog is unavailable. Try later."
                )
            return CatalogInfo(
                models=[ModelInfo.model_validate(item) for item in json.loads(data)],
                fetched_at=fetched,
                stale=now - fetched >= 900,
                ranking="Simulated catalog"
                if self.settings.provider_mode == "mock"
                else "OpenRouter most-popular",
            )
