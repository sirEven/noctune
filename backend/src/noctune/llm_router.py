"""LLM routing layer — sends prompts to local Ollama, cloud, or any OpenAI-compatible endpoint.

The router is transparent to the reconciliation pipeline. Same prompt schema
goes in, same Pydantic-validated response comes out. Config decides local vs cloud.
"""

import logging
from typing import Any

import httpx

from noctune.models.config import LLMConfig

logger = logging.getLogger(__name__)


class LLMRouter:
    """Routes LLM calls to the configured endpoint — local, cloud, or fallback."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.base_url: str
        self.model: str
        self.api_key: str = ""

        if config.direction == "local":
            self.base_url = config.local_base_url.rstrip("/")
            self.model = config.local_model
        else:
            self.base_url = config.cloud_base_url.rstrip("/")
            self.model = config.cloud_model
            self.api_key = config.cloud_api_key

    async def complete(self, prompt: str) -> str:
        """Send a chat completion request and return the response text.

        Tries the primary endpoint first, falls back to the other if configured.
        """
        try:
            return await self._call(self.base_url, self.model, self.api_key, prompt)
        except Exception as exc:
            logger.warning("Primary LLM endpoint failed: %s", exc)
            if self.config.fallback:
                return await self._fallback(prompt)
            raise

    async def _fallback(self, prompt: str) -> str:
        """Try the fallback endpoint."""
        if self.config.direction == "local" and self.config.fallback == "cloud":
            url = self.config.cloud_base_url.rstrip("/")
            model = self.config.cloud_model
            key = self.config.cloud_api_key
        elif self.config.direction == "cloud" and self.config.fallback == "local":
            url = self.config.local_base_url.rstrip("/")
            model = self.config.local_model
            key = ""
        else:
            raise RuntimeError(f"Unknown fallback configuration: {self.config.fallback}")

        logger.info("Trying fallback LLM endpoint: %s", url)
        return await self._call(url, model, key, prompt)

    async def _call(self, base_url: str, model: str, api_key: str, prompt: str) -> str:
        """Make an OpenAI-compatible chat completion call."""
        url = f"{base_url}/v1/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,  # Low temperature for deterministic tagging
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"]