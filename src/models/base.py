"""Abstract base adapter and shared dataclasses for LLM model integration."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class QuestionFormat(str, Enum):
    LIKERT = "likert"
    MULTIPLE_CHOICE = "multiple_choice"
    OPEN_ENDED = "open_ended"


@dataclass
class Question:
    id: str
    area: str
    text: str
    format: QuestionFormat
    region: str  # "us" or "global"
    # Likert-specific
    direction: Optional[str] = None  # "positive" or "negative" per axis
    axes: list[str] = field(default_factory=list)  # which axes this maps to
    # MC-specific
    options: Optional[dict[str, str]] = None  # label -> text
    option_scores: Optional[dict[str, dict[str, float]]] = None  # label -> {axis: score}


@dataclass
class ModelResponse:
    question_id: str
    raw_response: str
    parsed_value: Optional[str] = None  # Likert number, MC letter, or full text
    refused: bool = False
    error: Optional[str] = None


@dataclass
class RunConfig:
    model_id: str  # e.g. "openai:gpt-4o"
    system_prompt: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 1024


class BaseAdapter(abc.ABC):
    """Abstract base for LLM API adapters."""

    def __init__(self, model_name: str, api_key: Optional[str] = None):
        self.model_name = model_name
        self.api_key = api_key

    @abc.abstractmethod
    def query(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        """Send a prompt and return the raw text response."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model_name!r})"
