"""Abstract LLM client — supports DeepSeek, Kimi, and Anthropic via OpenAI-compatible API."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

# Provider → (base_url, env_var for API key, default model)
PROVIDERS = {
    "deepseek": (
        "https://api.deepseek.com",
        "DEEPSEEK_API_KEY",
        "deepseek-chat",
    ),
    "kimi": (
        "https://api.moonshot.cn/v1",
        "KIMI_API_KEY",
        "moonshot-v1-8k",
    ),
    "anthropic": (
        "https://api.anthropic.com/v1/",
        "ANTHROPIC_API_KEY",
        "claude-sonnet-4-20250514",
    ),
}


class LLMClient:
    """Thin wrapper around OpenAI-compatible chat completion APIs."""

    def __init__(
        self,
        provider: str = "deepseek",
        model: str | None = None,
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ):
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Choose from: {list(PROVIDERS)}")

        base_url, env_var, default_model = PROVIDERS[provider]
        api_key = os.environ.get(env_var)
        if not api_key:
            raise ValueError(f"Missing API key: set {env_var} in .env")

        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=90.0)
        self.model = model or default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider = provider

    def generate(
        self,
        prompt: str,
        system: str = "",
    ) -> str:
        """Send a chat completion request and return the response text."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content.strip()

    def generate_json(
        self,
        prompt: str,
        system: str = "",
        retries: int = 2,
    ) -> dict[str, Any]:
        """Generate and parse a JSON response from the LLM.

        Retries up to `retries` times on JSONDecodeError (handles transient
        DeepSeek refusals or truncated responses).
        """
        import logging
        logger = logging.getLogger("zcyber.llm")

        last_err: Exception | None = None
        for attempt in range(1, retries + 2):
            raw = self.generate(prompt, system)

            # Strip markdown code fences if present
            if "```" in raw:
                lines = raw.split("\n")
                lines = [line for line in lines if not line.strip().startswith("```")]
                raw = "\n".join(lines)

            # Extract JSON object if LLM wrapped it in extra text
            brace_start = raw.find("{")
            brace_end = raw.rfind("}")
            if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
                raw = raw[brace_start : brace_end + 1]

            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                last_err = exc
                if attempt <= retries:
                    logger.warning(
                        f"JSONDecodeError on attempt {attempt}, retrying... "
                        f"(snippet: {raw[:80]!r})"
                    )

        raise json.JSONDecodeError(
            f"Failed to parse JSON after {retries + 1} attempts: {last_err}",
            "",
            0,
        ) from last_err

    @classmethod
    def from_config(cls, config: dict) -> LLMClient:
        """Create an LLMClient from config.yaml's llm section."""
        return cls(
            provider=config.get("provider", "deepseek"),
            model=config.get("model"),
            temperature=config.get("temperature", 0.8),
            max_tokens=config.get("max_tokens", 2000),
        )
