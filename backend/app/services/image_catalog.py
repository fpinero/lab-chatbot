"""Normalize dedicated image capabilities, with durable stale catalog fallback."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.auth.service import AuthError
from app.config import Settings
from app.models import CatalogCache
from app.providers.chat import ProviderError
from app.providers.images import MODEL_PATTERN, ImageProvider


class Capability(BaseModel):
    type: Literal["enum", "range", "boolean"]
    values: list[str] = Field(default_factory=list, max_length=100)
    min: int | None = None
    max: int | None = None


class ImageModelInfo(BaseModel):
    id: str = Field(pattern=f"^{MODEL_PATTERN}$", max_length=200)
    name: str = Field(max_length=200)
    api_family: Literal["images"] = "images"
    input_modalities: list[str]
    simulated: bool


class ImagePricing(BaseModel):
    billable: str = Field(max_length=100)
    unit: str = Field(max_length=100)
    cost_usd: Decimal = Field(ge=0, le=10000, allow_inf_nan=False)
    variant: str | None = Field(default=None, max_length=100)


class ImageEndpoint(BaseModel):
    provider_name: str = Field(max_length=200)
    provider_tag: str = Field(pattern=r"^[A-Za-z0-9._:/-]{1,200}$")
    parameters: dict[str, Capability]
    pricing: list[ImagePricing] = Field(max_length=100)


class ImageCatalogInfo(BaseModel):
    models: list[ImageModelInfo]
    fetched_at: int
    stale: bool
    ranking: str


class ImageEndpointInfo(BaseModel):
    model: ImageModelInfo
    endpoints: list[ImageEndpoint]
    fetched_at: int
    stale: bool
    max_images: int


class ImageCatalog:
    def __init__(
        self, engine: Engine, settings: Settings, provider: ImageProvider, now: Callable[[], int]
    ) -> None:
        self.engine, self.settings, self.provider, self.now = engine, settings, provider, now
        self.lock = asyncio.Lock()

    async def cached(
        self,
        family: str,
        fetch: Callable[[], Awaitable[list[dict[str, Any]]]],
        refresh: bool = False,
    ) -> tuple[list[dict[str, Any]], int, bool]:
        if (
            self.settings.provider_mode == "openrouter"
            and not self.settings.openrouter_api_key.get_secret_value()
        ):
            raise AuthError(
                503, "provider_unconfigured", "Configure a restricted provider key first."
            )
        async with self.lock:
            now = self.now()
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
                if refresh and attempt and now - attempt < 60:
                    raise AuthError(
                        429, "catalog_throttled", "Wait before refreshing the image catalog again."
                    )
                should_fetch = refresh or (
                    (not fetched or now - fetched >= 900) and now - attempt >= 60
                )
                if should_fetch:
                    cached.last_attempt_at = now
                    db.commit()
            if should_fetch:
                try:
                    values = await fetch()
                    if not values:
                        raise ProviderError("catalog_invalid")
                    data, fetched = json.dumps(values, default=str), now
                    with Session(self.engine) as db:
                        row = db.get(CatalogCache, family)
                        if row:
                            row.catalog_json, row.fetched_at = data, fetched
                            db.commit()
                except ProviderError:
                    if not fetched:
                        raise AuthError(
                            503,
                            "image_catalog_unavailable",
                            "Image capabilities are unavailable. Try later.",
                        ) from None
            if not fetched:
                raise AuthError(
                    503,
                    "image_catalog_unavailable",
                    "Image capabilities are unavailable. Try later.",
                )
            return list(json.loads(data)), fetched, now - fetched >= 900

    async def get(self, refresh: bool = False) -> ImageCatalogInfo:
        async def fetch() -> list[dict[str, Any]]:
            result = []
            for raw in await self.provider.catalog():
                try:
                    architecture = raw["architecture"]
                    if (
                        "image" not in architecture["output_modalities"]
                        or "text" not in architecture["input_modalities"]
                    ):
                        continue
                    model = ImageModelInfo(
                        id=raw["id"],
                        name=raw["name"],
                        input_modalities=architecture["input_modalities"],
                        simulated=self.settings.provider_mode == "mock",
                    )
                    if (
                        self.settings.model_allowlist
                        and model.id not in self.settings.model_allowlist
                    ):
                        continue
                    result.append(model.model_dump())
                except (ValidationError, KeyError, TypeError):
                    continue
            return result

        values, fetched, stale = await self.cached("images", fetch, refresh)
        models = [ImageModelInfo.model_validate(value) for value in values]
        return ImageCatalogInfo(
            models=models,
            fetched_at=fetched,
            stale=stale,
            ranking="Simulated catalog"
            if self.settings.provider_mode == "mock"
            else "Available image models (catalog order)",
        )

    async def endpoints(self, model_id: str) -> ImageEndpointInfo:
        if not re.fullmatch(MODEL_PATTERN, model_id):
            raise AuthError(422, "invalid_model", "Choose a model from the image catalog.")
        model = next((model for model in (await self.get()).models if model.id == model_id), None)
        if not model:
            raise AuthError(422, "invalid_model", "Choose a model from the image catalog.")

        async def fetch() -> list[dict[str, Any]]:
            result = []
            for raw in await self.provider.endpoints(model_id):
                try:
                    params = {}
                    for key, value in raw["supported_parameters"].items():
                        try:
                            params[key] = Capability.model_validate(value)
                        except ValidationError:
                            continue
                    endpoint = ImageEndpoint(
                        provider_name=raw["provider_name"],
                        provider_tag=raw["provider_tag"],
                        parameters=params,
                        pricing=raw.get("pricing", []),
                    )
                    if any(
                        price.cost_usd > self.settings.image_price_ceiling_usd
                        for price in endpoint.pricing
                    ):
                        continue
                    result.append(endpoint.model_dump(mode="json"))
                except (ValidationError, KeyError, TypeError, AttributeError):
                    continue
            return result

        values, fetched, stale = await self.cached(f"images:{model_id}", fetch)
        return ImageEndpointInfo(
            model=model,
            endpoints=[ImageEndpoint.model_validate(value) for value in values],
            fetched_at=fetched,
            stale=stale,
            max_images=self.settings.max_generated_images,
        )
