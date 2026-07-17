"""Loading of user-defined, OpenAI-compatible providers from a local YAML file.

The file is gitignored and holds server details that are specific to a machine or
deployment, e.g.:

    providers:
      myserver:
        base_url: https://llm.internal/v1
        api_key_env: MYSERVER_API_KEY
        default_model: llama-3.3-70b
"""

import os
from pathlib import Path
from dataclasses import dataclass

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

CUSTOM_PROVIDERS_PATH = Path(__file__).parents[1] / "custom_providers.yaml"

# Sent instead of a real key when a provider needs no authentication. Passing None
# would make OpenAIProvider fall back to OPENAI_API_KEY, leaking it to the server.
_NO_API_KEY = "api-key-not-set"


class CustomProviderError(Exception):
    """Raised when the custom providers file is missing, malformed or incomplete."""


class CustomProviderConfig(BaseModel):
    """Details of a single user-defined OpenAI-compatible server."""

    model_config = {"extra": "forbid"}

    base_url: str
    default_model: str | None = None
    api_key: str | None = None
    api_key_env: str | None = Field(
        default=None,
        description="Name of an environment variable holding the API key.",
    )

    @model_validator(mode="after")
    def _check_single_key_source(self) -> "CustomProviderConfig":
        if self.api_key is not None and self.api_key_env is not None:
            raise ValueError("provide at most one of 'api_key' and 'api_key_env'")
        return self

    def resolve_api_key(self, provider_name: str) -> str:
        """Return the API key, or a placeholder if the server needs no authentication."""
        if self.api_key is not None:
            return self.api_key
        if self.api_key_env is not None:
            key = os.getenv(self.api_key_env)
            if not key:
                raise CustomProviderError(
                    f"Provider '{provider_name}' sets api_key_env: '{self.api_key_env}', "
                    f"but that environment variable is not set."
                )
            return key
        return _NO_API_KEY


@dataclass
class CustomProviders:
    """The contents of the custom providers file."""

    providers: dict[str, CustomProviderConfig]
    path: Path

    @classmethod
    def load(cls, path: Path = CUSTOM_PROVIDERS_PATH) -> "CustomProviders":
        if not path.exists():
            return cls(providers={}, path=path)
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as exc:
            raise CustomProviderError(f"Could not parse {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise CustomProviderError(f"{path} must contain a mapping at the top level.")

        entries = raw.get("providers") or {}
        if not isinstance(entries, dict):
            raise CustomProviderError(f"The 'providers' key in {path} must be a mapping.")

        providers = {}
        for name, entry in entries.items():
            if not isinstance(entry, dict):
                raise CustomProviderError(
                    f"Provider '{name}' in {path} must be a mapping of settings."
                )
            try:
                providers[str(name)] = CustomProviderConfig(**entry)
            except ValidationError as exc:
                raise CustomProviderError(f"Invalid config for provider '{name}' in {path}:\n{exc}") from exc
        return cls(providers=providers, path=path)

    def get(self, name: str) -> CustomProviderConfig:
        try:
            return self.providers[name]
        except KeyError:
            raise CustomProviderError(self._unknown_message(name)) from None

    def _unknown_message(self, name: str) -> str:
        if not self.providers:
            return (
                f"Unknown provider '{name}', and no custom providers are defined. "
                f"Create {self.path} to define one."
            )
        known = ", ".join(sorted(self.providers))
        return (
            f"Unknown provider '{name}'. Custom providers defined in {self.path}: {known}."
        )
