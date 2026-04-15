"""OpenAI-compatible API adapter (also supports Azure AI Foundry and other compatible APIs)."""

from __future__ import annotations

import os
from typing import Optional

from openai import OpenAI

from .base import BaseAdapter


class OpenAIAdapter(BaseAdapter):
    """Adapter for OpenAI and OpenAI-compatible APIs."""

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        use_max_completion_tokens: bool = False,
        skip_temperature: bool = False,
    ):
        super().__init__(model_name, api_key)
        self._use_max_completion_tokens = use_max_completion_tokens
        self._skip_temperature = skip_temperature
        self.client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url,
        )

    def query(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        kwargs: dict = {
            "model": self.model_name,
            "messages": messages,
        }
        if not self._skip_temperature:
            kwargs["temperature"] = temperature
        if self._use_max_completion_tokens:
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
