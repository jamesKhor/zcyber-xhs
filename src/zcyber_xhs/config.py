"""Configuration loader — reads config.yaml and .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def _resolve_env_vars(value: Any) -> Any:
    """Resolve ${VAR:-default} patterns in config values."""
    if isinstance(value, str) and "${" in value:
        import re

        def _replace(match: re.Match) -> str:
            expr = match.group(1)
            if ":-" in expr:
                var, default = expr.split(":-", 1)
                return os.environ.get(var, default)
            return os.environ.get(expr, match.group(0))

        return re.sub(r"\$\{([^}]+)\}", _replace, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


class Config:
    """Central configuration object."""

    def __init__(self, config_path: str | Path | None = None):
        load_dotenv()

        if config_path is None:
            config_path = self._find_config()

        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        self._data = _resolve_env_vars(raw)
        self._base_dir = Path(config_path).parent.parent

    @staticmethod
    def _find_config() -> Path:
        """Walk up from cwd to find config/config.yaml."""
        current = Path.cwd()
        for parent in [current, *current.parents]:
            candidate = parent / "config" / "config.yaml"
            if candidate.exists():
                return candidate
        raise FileNotFoundError("config/config.yaml not found")

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def llm(self) -> dict:
        return self._data.get("llm", {})

    @property
    def schedule(self) -> dict:
        return self._data.get("schedule", {})

    @property
    def publishing(self) -> dict:
        return self._data.get("publishing", {})

    @property
    def content(self) -> dict:
        return self._data.get("content", {})

    @property
    def images(self) -> dict:
        return self._data.get("images", {})

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Access nested config via dot notation: 'llm.provider'."""
        keys = dotted_key.split(".")
        value = self._data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value
