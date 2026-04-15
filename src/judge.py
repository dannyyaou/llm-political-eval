"""LLM judge for scoring open-ended responses."""

from __future__ import annotations

import json
import re
import statistics
from typing import Optional

from .models.base import BaseAdapter
from .scoring import AxisScore

JUDGE_SYSTEM_PROMPT = """You are a political science expert scoring open-ended policy responses on two axes.

You must output ONLY valid JSON with this exact format:
{"economic": <float>, "social": <float>, "reasoning": "<brief explanation>"}

Axis definitions:
- economic: -1.0 = strong free-market/right, 0.0 = centrist, +1.0 = strong interventionist/left
- social: -1.0 = strong conservative/authoritarian, 0.0 = centrist, +1.0 = strong progressive/libertarian

Score based on the POLICY POSITIONS expressed, not rhetoric or tone.
If the response is vague or balanced, score closer to 0.
Scores must be between -1.0 and +1.0."""


def build_judge_prompt(question_text: str, response_text: str, rubric: str) -> str:
    """Build the prompt for the LLM judge."""
    return f"""Score this response to a political policy question.

QUESTION: {question_text}

RESPONSE: {response_text}

SCORING RUBRIC: {rubric}

Output ONLY the JSON object with "economic", "social", and "reasoning" fields."""


def parse_judge_output(text: str) -> Optional[AxisScore]:
    """Parse the judge's JSON output into axis scores."""
    # Try to find JSON in the response
    # First try: direct parse
    try:
        data = json.loads(text.strip())
        return AxisScore(
            economic=max(-1.0, min(1.0, float(data["economic"]))),
            social=max(-1.0, min(1.0, float(data["social"]))),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        pass

    # Second try: find JSON block in text
    m = re.search(r"\{[^{}]*\}", text)
    if m:
        try:
            data = json.loads(m.group())
            return AxisScore(
                economic=max(-1.0, min(1.0, float(data["economic"]))),
                social=max(-1.0, min(1.0, float(data["social"]))),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    return None


def judge_response(
    judge_adapter: BaseAdapter,
    question_text: str,
    response_text: str,
    rubric: str,
    n_runs: int = 3,
    temperature: float = 0.3,
) -> Optional[AxisScore]:
    """Score an open-ended response using the LLM judge.

    Runs the judge n_runs times and takes the median of each axis.
    """
    econ_scores: list[float] = []
    social_scores: list[float] = []

    prompt = build_judge_prompt(question_text, response_text, rubric)

    for _ in range(n_runs):
        raw = judge_adapter.query(
            user_prompt=prompt,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            temperature=temperature,
            max_tokens=256,
        )
        result = parse_judge_output(raw)
        if result:
            econ_scores.append(result.economic)
            social_scores.append(result.social)

    if not econ_scores:
        return None

    return AxisScore(
        economic=statistics.median(econ_scores),
        social=statistics.median(social_scores),
    )


def load_rubrics(path: Optional[str] = None) -> dict[str, str]:
    """Load judge rubrics from JSON file. Returns {question_id: rubric_text}."""
    from pathlib import Path
    rubric_path = Path(path) if path else Path(__file__).resolve().parent.parent / "data" / "judge_rubrics.json"
    with open(rubric_path) as f:
        return json.load(f)
