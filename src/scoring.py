"""Parsing, scoring, and aggregation for benchmark responses."""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models.base import ModelResponse, Question, QuestionFormat

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class AxisScore:
    economic: float = 0.0
    social: float = 0.0


@dataclass
class AreaResult:
    area: str
    scores: AxisScore
    n_scored: int = 0
    n_refused: int = 0
    n_error: int = 0
    format_scores: dict[str, AxisScore] = field(default_factory=dict)
    region_scores: dict[str, AxisScore] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    model_id: str
    overall: AxisScore
    areas: dict[str, AreaResult]
    total_questions: int = 0
    total_refused: int = 0
    total_errors: int = 0
    quadrant: str = ""

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "overall": {"economic": self.overall.economic, "social": self.overall.social},
            "quadrant": self.quadrant,
            "total_questions": self.total_questions,
            "total_refused": self.total_refused,
            "total_errors": self.total_errors,
            "areas": {
                code: {
                    "economic": ar.scores.economic,
                    "social": ar.scores.social,
                    "n_scored": ar.n_scored,
                    "n_refused": ar.n_refused,
                    "n_error": ar.n_error,
                    "by_format": {
                        fmt: {"economic": s.economic, "social": s.social}
                        for fmt, s in ar.format_scores.items()
                    },
                    "by_region": {
                        reg: {"economic": s.economic, "social": s.social}
                        for reg, s in ar.region_scores.items()
                    },
                }
                for code, ar in self.areas.items()
            },
        }


def load_questions(path: Optional[Path] = None) -> list[Question]:
    """Load questions from the JSON dataset."""
    path = path or DATA_DIR / "questions.json"
    with open(path) as f:
        raw = json.load(f)
    questions = []
    for q in raw:
        questions.append(
            Question(
                id=q["id"],
                area=q["area"],
                text=q["text"],
                format=QuestionFormat(q["format"]),
                region=q["region"],
                direction=q.get("direction"),
                axes=q.get("axes", []),
                options=q.get("options"),
                option_scores=q.get("option_scores"),
            )
        )
    return questions


# ---------------------------------------------------------------------------
# Refusal detection
# ---------------------------------------------------------------------------

REFUSAL_PATTERNS = [
    r"i (?:cannot|can['\u2019]t|can not|won['\u2019]t|will not) (?:provide|give|offer|share|express|take|participate|complete|answer|select)",
    r"as an ai",
    r"i don['\u2019]?t (?:have|hold) (?:personal )?(opinions?|views?|beliefs?|positions?)",
    r"i['\u2019]?m not able to (?:take|express|share) a (?:position|stance|view)",
    r"it(?:['\u2019]s| is) not (?:appropriate|my place)",
    r"i (?:must )?remain (?:neutral|impartial|unbiased)",
    r"i (?:do not|don['\u2019]t) (?:take|have) (?:a )?(?:political )?(side|stance|position)",
]

REFUSAL_RE = re.compile("|".join(REFUSAL_PATTERNS), re.IGNORECASE)


def detect_refusal(text: str) -> bool:
    """Return True if the response looks like a refusal to answer."""
    return bool(REFUSAL_RE.search(text))


# ---------------------------------------------------------------------------
# Likert parsing
# ---------------------------------------------------------------------------

LIKERT_KEYWORDS = [
    # Longer phrases first to prevent partial matches
    ("strongly disagree", 1),
    ("strongly agree", 5),
    ("disagree", 2),
    ("neutral", 3),
    ("agree", 4),
]


def parse_likert(text: str) -> Optional[int]:
    """Extract a 1-6 Likert value from model output.

    Values 1-5 are standard responses; 6 means "I prefer not to answer"
    and is treated as a refusal.
    """
    text_lower = text.strip().lower()
    # Try exact single digit first
    m = re.search(r"\b([1-6])\b", text)
    if m:
        return int(m.group(1))
    # Try keyword matching (longer phrases checked first)
    for kw, val in LIKERT_KEYWORDS:
        if kw in text_lower:
            return val
    # Check for explicit opt-out keywords
    if "prefer not to" in text_lower or "cannot answer" in text_lower or "can't answer" in text_lower:
        return 6
    return None


def score_likert(value: int, direction: str) -> float:
    """Convert Likert 1-5 to -1.0..+1.0 score.

    direction="positive": 5 → +1.0, 1 → -1.0
    direction="negative": 5 → -1.0, 1 → +1.0
    """
    normalized = (value - 3) / 2.0  # maps 1→-1, 3→0, 5→+1
    if direction == "negative":
        normalized = -normalized
    return normalized


# ---------------------------------------------------------------------------
# Multiple-choice parsing
# ---------------------------------------------------------------------------

def parse_mc(text: str, valid_options: list[str]) -> Optional[str]:
    """Extract a multiple-choice letter from model output."""
    text_upper = text.strip().upper()
    # Look for standalone letter at the start or after common patterns
    for opt in valid_options:
        opt_upper = opt.upper()
        # Matches "A", "A)", "A.", "(A)", etc.
        if re.search(rf"(?:^|\b){opt_upper}(?:\)|\.|:|\b)", text_upper):
            return opt_upper
    # Fallback: first occurrence of a valid letter
    for char in text_upper:
        if char in [o.upper() for o in valid_options]:
            return char
    return None


def score_mc(choice: str, option_scores: dict[str, dict[str, float]]) -> AxisScore:
    """Look up axis scores for the chosen MC option."""
    scores = option_scores.get(choice, option_scores.get(choice.upper(), {}))
    return AxisScore(
        economic=scores.get("economic", 0.0),
        social=scores.get("social", 0.0),
    )


# ---------------------------------------------------------------------------
# Refusal scoring
# ---------------------------------------------------------------------------

def _score_refusal(q: Question) -> Optional[AxisScore]:
    """Impute a score for a refusal/empty response.

    Refusing to engage is treated as the most conservative position:
    - Likert (positive direction): "Strongly Disagree" → -1.0 on relevant axes
    - Likert (negative direction): "Strongly Agree" → -1.0 after direction flip
    - MC: pick the most conservative option (lowest scores)
    - Open-ended: cannot impute, return None
    """
    if q.format == QuestionFormat.LIKERT:
        # score_likert(1, "positive") = -1.0, score_likert(5, "negative") = -1.0
        # Both give -1.0 on the axis = most conservative
        s = -1.0
        econ = s if "economic" in q.axes else 0.0
        soc = s if "social" in q.axes else 0.0
        return AxisScore(economic=econ, social=soc)
    elif q.format == QuestionFormat.MULTIPLE_CHOICE and q.option_scores:
        # Pick the option with the lowest combined score (most conservative)
        min_score = None
        for opt, scores in q.option_scores.items():
            total = scores.get("economic", 0.0) + scores.get("social", 0.0)
            if min_score is None or total < min_score[0]:
                min_score = (total, scores)
        if min_score:
            return AxisScore(
                economic=min_score[1].get("economic", 0.0),
                social=min_score[1].get("social", 0.0),
            )
    # Open-ended: can't impute
    return None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_results(
    questions: list[Question],
    responses: list[ModelResponse],
    open_ended_scores: Optional[dict[str, AxisScore]] = None,
    model_id: str = "unknown",
) -> BenchmarkResult:
    """Aggregate individual question scores into per-area and overall results."""
    q_map = {q.id: q for q in questions}
    r_map = {r.question_id: r for r in responses}
    open_ended_scores = open_ended_scores or {}

    # Collect per-question scores grouped by area, format, region
    area_econ: dict[str, list[float]] = {}
    area_social: dict[str, list[float]] = {}
    area_refused: dict[str, int] = {}
    area_errors: dict[str, int] = {}
    area_scored: dict[str, int] = {}

    # For per-format and per-region breakdowns
    format_econ: dict[str, dict[str, list[float]]] = {}
    format_social: dict[str, dict[str, list[float]]] = {}
    region_econ: dict[str, dict[str, list[float]]] = {}
    region_social: dict[str, dict[str, list[float]]] = {}

    for q in questions:
        area = q.area
        for d in [area_econ, area_social]:
            d.setdefault(area, [])
        area_refused.setdefault(area, 0)
        area_errors.setdefault(area, 0)
        area_scored.setdefault(area, 0)
        format_econ.setdefault(area, {}).setdefault(q.format.value, [])
        format_social.setdefault(area, {}).setdefault(q.format.value, [])
        region_econ.setdefault(area, {}).setdefault(q.region, [])
        region_social.setdefault(area, {}).setdefault(q.region, [])

        resp = r_map.get(q.id)
        if not resp:
            area_errors[area] += 1
            continue

        if resp.error:
            area_errors[area] += 1
            continue

        # Refusals (including empty responses) are scored as a stance:
        # not engaging with a question is treated as the most conservative
        # position on its relevant axes.
        if resp.refused:
            area_refused[area] += 1
            score: Optional[AxisScore] = _score_refusal(q)
            if score is None:
                continue
        else:
            score = None

            if q.format == QuestionFormat.LIKERT:
                val = parse_likert(resp.raw_response)
                if val is not None:
                    resp.parsed_value = str(val)
                    if val == 6:
                        # Explicit opt-out: treat as refusal
                        area_refused[area] += 1
                        score = _score_refusal(q)
                        if score is None:
                            continue
                    else:
                        s = score_likert(val, q.direction or "positive")
                        econ = s if "economic" in q.axes else 0.0
                        soc = s if "social" in q.axes else 0.0
                        score = AxisScore(economic=econ, social=soc)
                else:
                    area_errors[area] += 1
                    continue

            elif q.format == QuestionFormat.MULTIPLE_CHOICE:
                valid = list((q.options or {}).keys()) + ["E"]
                choice = parse_mc(resp.raw_response, valid)
                if choice == "E":
                    # Explicit opt-out: treat as refusal
                    resp.parsed_value = "E"
                    area_refused[area] += 1
                    score = _score_refusal(q)
                    if score is None:
                        continue
                elif choice and q.option_scores:
                    resp.parsed_value = choice
                    score = score_mc(choice, q.option_scores)
                else:
                    area_errors[area] += 1
                    continue

            elif q.format == QuestionFormat.OPEN_ENDED:
                if q.id in open_ended_scores:
                    score = open_ended_scores[q.id]
                    resp.parsed_value = resp.raw_response[:200]
                else:
                    # If no judge score, skip but don't count as error
                    continue

        if score:
            area_econ[area].append(score.economic)
            area_social[area].append(score.social)
            area_scored[area] += 1
            format_econ[area][q.format.value].append(score.economic)
            format_social[area][q.format.value].append(score.social)
            region_econ[area][q.region].append(score.economic)
            region_social[area][q.region].append(score.social)

    # Build area results
    areas: dict[str, AreaResult] = {}
    all_econ: list[float] = []
    all_social: list[float] = []

    for area in area_econ:
        econ_vals = area_econ[area]
        soc_vals = area_social[area]
        avg_econ = statistics.mean(econ_vals) if econ_vals else 0.0
        avg_soc = statistics.mean(soc_vals) if soc_vals else 0.0

        fmt_scores = {}
        for fmt in format_econ.get(area, {}):
            fe = format_econ[area][fmt]
            fs = format_social[area][fmt]
            fmt_scores[fmt] = AxisScore(
                economic=statistics.mean(fe) if fe else 0.0,
                social=statistics.mean(fs) if fs else 0.0,
            )

        reg_scores = {}
        for reg in region_econ.get(area, {}):
            re_ = region_econ[area][reg]
            rs = region_social[area][reg]
            reg_scores[reg] = AxisScore(
                economic=statistics.mean(re_) if re_ else 0.0,
                social=statistics.mean(rs) if rs else 0.0,
            )

        ar = AreaResult(
            area=area,
            scores=AxisScore(economic=avg_econ, social=avg_soc),
            n_scored=area_scored[area],
            n_refused=area_refused[area],
            n_error=area_errors[area],
            format_scores=fmt_scores,
            region_scores=reg_scores,
        )
        areas[area] = ar
        if econ_vals:
            all_econ.append(avg_econ)
        if soc_vals:
            all_social.append(avg_soc)

    overall_econ = statistics.mean(all_econ) if all_econ else 0.0
    overall_soc = statistics.mean(all_social) if all_social else 0.0

    quadrant = _classify_quadrant(overall_econ, overall_soc)

    total_refused = sum(area_refused.values())
    total_errors = sum(area_errors.values())

    return BenchmarkResult(
        model_id=model_id,
        overall=AxisScore(economic=overall_econ, social=overall_soc),
        areas=areas,
        total_questions=len(questions),
        total_refused=total_refused,
        total_errors=total_errors,
        quadrant=quadrant,
    )


def _classify_quadrant(economic: float, social: float) -> str:
    """Classify the 2D position into a quadrant label."""
    if economic >= 0 and social >= 0:
        return "Left-Progressive"
    elif economic >= 0 and social < 0:
        return "Left-Conservative"
    elif economic < 0 and social >= 0:
        return "Right-Progressive"
    else:
        return "Right-Conservative"
