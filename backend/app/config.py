from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_origin: str = "http://127.0.0.1:5173"
    provider_mode: Literal["mock", "openrouter"] = "mock"

    @model_validator(mode="after")
    def validate_bootstrap(self) -> "Settings":
        if self.app_env == "production":
            raise ValueError("Production is unavailable until authentication is configured.")
        if self.provider_mode != "mock":
            raise ValueError("Live providers are unavailable in this bootstrap milestone.")
        return self
