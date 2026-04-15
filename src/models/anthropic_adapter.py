"""Anthropic API adapter."""

from __future__ import annotations

import os
from typing import Optional

import anthropic

from .base import BaseAdapter


class AnthropicAdapter(BaseAdapter):
    """Adapter for the Anthropic Messages API."""

    def __init__(self, model_name: str, api_key: Optional[str] = None, base_url: Optional[str] = None):
        super().__init__(model_name, api_key)
        kwargs: dict = {
            "api_key": api_key or os.environ.get("ANTHROPIC_API_KEY"),
        }
        base = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        if base:
            kwargs["base_url"] = base
        self.client = anthropic.Anthropic(**kwargs)

    def query(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        kwargs: dict = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if temperature > 0:
            kwargs["temperature"] = temperature
        if system_prompt:
            kwargs["system"] = system_prompt

        message = self.client.messages.create(**kwargs)
        return message.content[0].text if message.content else ""
