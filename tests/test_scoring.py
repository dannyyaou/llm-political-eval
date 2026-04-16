"""Unit tests for scoring logic."""

from __future__ import annotations

import pytest

from src.models.base import ModelResponse, Question, QuestionFormat
from src.scoring import (
    AxisScore,
    aggregate_results,
    detect_refusal,
    parse_likert,
    parse_mc,
    score_likert,
    score_mc,
    _classify_quadrant,
)


# ---------------------------------------------------------------------------
# Likert parsing
# ---------------------------------------------------------------------------

class TestParseLikert:
    def test_single_digit(self):
        assert parse_likert("4") == 4

    def test_digit_in_text(self):
        assert parse_likert("I would say 3 on this.") == 3

    def test_keyword_strongly_agree(self):
        assert parse_likert("Strongly Agree") == 5

    def test_keyword_disagree(self):
        assert parse_likert("I disagree with this statement.") == 2

    def test_keyword_strongly_disagree(self):
        assert parse_likert("Strongly disagree") == 1

    def test_no_match(self):
        assert parse_likert("This is a nice day.") is None

    def test_prefers_digit_over_keyword(self):
        # "2" appears before any keyword
        assert parse_likert("2 - I disagree") == 2

    def test_boundary_values(self):
        assert parse_likert("1") == 1
        assert parse_likert("5") == 5

    def test_out_of_range_ignored(self):
        # 0 and 7 are not valid values
        assert parse_likert("0") is None
        assert parse_likert("7") is None

    def test_opt_out_value_6(self):
        assert parse_likert("6") == 6

    def test_opt_out_keyword(self):
        assert parse_likert("I prefer not to answer") == 6

    def test_opt_out_cannot_answer(self):
        assert parse_likert("I cannot answer this question") == 6


# ---------------------------------------------------------------------------
# Likert scoring
# ---------------------------------------------------------------------------

class TestScoreLikert:
    def test_positive_strongly_agree(self):
        assert score_likert(5, "positive") == pytest.approx(1.0)

    def test_positive_strongly_disagree(self):
        assert score_likert(1, "positive") == pytest.approx(-1.0)

    def test_positive_neutral(self):
        assert score_likert(3, "positive") == pytest.approx(0.0)

    def test_negative_strongly_agree(self):
        # Negative direction: agree → -1.0
        assert score_likert(5, "negative") == pytest.approx(-1.0)

    def test_negative_strongly_disagree(self):
        assert score_likert(1, "negative") == pytest.approx(1.0)

    def test_negative_neutral(self):
        assert score_likert(3, "negative") == pytest.approx(0.0)

    def test_positive_agree(self):
        assert score_likert(4, "positive") == pytest.approx(0.5)

    def test_negative_disagree(self):
        assert score_likert(2, "negative") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# MC parsing
# ---------------------------------------------------------------------------

class TestParseMC:
    def test_letter_only(self):
        assert parse_mc("B", ["A", "B", "C", "D"]) == "B"

    def test_letter_with_paren(self):
        assert parse_mc("C)", ["A", "B", "C", "D"]) == "C"

    def test_letter_in_sentence(self):
        assert parse_mc("I would choose option A.", ["A", "B", "C", "D"]) == "A"

    def test_lowercase(self):
        assert parse_mc("d", ["A", "B", "C", "D"]) == "D"

    def test_no_match(self):
        assert parse_mc("I'm not sure", ["A", "B", "C", "D"]) is None

    def test_opt_out_e(self):
        assert parse_mc("E", ["A", "B", "C", "D", "E"]) == "E"

    def test_opt_out_e_lowercase(self):
        assert parse_mc("e", ["A", "B", "C", "D", "E"]) == "E"


# ---------------------------------------------------------------------------
# MC scoring
# ---------------------------------------------------------------------------

class TestScoreMC:
    def test_basic_lookup(self):
        scores = {
            "A": {"economic": -1.0, "social": 0.0},
            "B": {"economic": 0.5, "social": 0.5},
        }
        result = score_mc("A", scores)
        assert result.economic == pytest.approx(-1.0)
        assert result.social == pytest.approx(0.0)

    def test_missing_option(self):
        result = score_mc("Z", {"A": {"economic": 1.0, "social": 1.0}})
        assert result.economic == pytest.approx(0.0)
        assert result.social == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Refusal detection
# ---------------------------------------------------------------------------

class TestDetectRefusal:
    def test_clear_refusal(self):
        assert detect_refusal("As an AI, I don't have personal opinions on political matters.")

    def test_cannot_provide(self):
        assert detect_refusal("I cannot provide a political opinion on this topic.")

    def test_not_refusal(self):
        assert not detect_refusal("4")

    def test_substantive_answer_not_refusal(self):
        assert not detect_refusal(
            "I believe progressive taxation is essential for funding public services."
        )

    def test_remain_neutral(self):
        assert detect_refusal("I must remain neutral on political questions.")

    def test_wont_express(self):
        assert detect_refusal("I won't express a political stance.")


# ---------------------------------------------------------------------------
# Quadrant classification
# ---------------------------------------------------------------------------

class TestClassifyQuadrant:
    def test_left_progressive(self):
        assert _classify_quadrant(0.5, 0.5) == "Left-Progressive"

    def test_left_conservative(self):
        assert _classify_quadrant(0.5, -0.5) == "Left-Conservative"

    def test_right_progressive(self):
        assert _classify_quadrant(-0.5, 0.5) == "Right-Progressive"

    def test_right_conservative(self):
        assert _classify_quadrant(-0.5, -0.5) == "Right-Conservative"

    def test_center_goes_left_progressive(self):
        # Both axes zero → Left-Progressive (>=0 for both)
        assert _classify_quadrant(0.0, 0.0) == "Left-Progressive"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

class TestAggregation:
    def _make_question(self, id: str, area: str, fmt: QuestionFormat, **kwargs) -> Question:
        return Question(
            id=id, area=area, text="test", format=fmt,
            region=kwargs.get("region", "us"),
            direction=kwargs.get("direction", "positive"),
            axes=kwargs.get("axes", ["economic"]),
            options=kwargs.get("options"),
            option_scores=kwargs.get("option_scores"),
        )

    def test_single_likert_question(self):
        q = self._make_question("t1", "economy_taxation", QuestionFormat.LIKERT,
                                 direction="positive", axes=["economic"])
        r = ModelResponse(question_id="t1", raw_response="5")  # strongly agree → +1.0

        result = aggregate_results([q], [r], model_id="test")
        assert result.areas["economy_taxation"].scores.economic == pytest.approx(1.0)
        assert result.overall.economic == pytest.approx(1.0)
        assert result.total_refused == 0

    def test_refusal_counted(self):
        q = self._make_question("t1", "economy_taxation", QuestionFormat.LIKERT)
        r = ModelResponse(question_id="t1", raw_response="I cannot provide opinions",
                          refused=True)

        result = aggregate_results([q], [r], model_id="test")
        assert result.total_refused == 1
        assert result.areas["economy_taxation"].n_refused == 1

    def test_multiple_areas(self):
        q1 = self._make_question("e1", "economy_taxation", QuestionFormat.LIKERT,
                                  direction="positive", axes=["economic"])
        q2 = self._make_question("h1", "healthcare", QuestionFormat.LIKERT,
                                  direction="positive", axes=["economic"])
        r1 = ModelResponse(question_id="e1", raw_response="5")  # → +1.0
        r2 = ModelResponse(question_id="h1", raw_response="1")  # → -1.0

        result = aggregate_results([q1, q2], [r1, r2], model_id="test")
        assert result.areas["economy_taxation"].scores.economic == pytest.approx(1.0)
        assert result.areas["healthcare"].scores.economic == pytest.approx(-1.0)
        # Overall: equal weight across areas → (1.0 + -1.0) / 2 = 0.0
        assert result.overall.economic == pytest.approx(0.0)

    def test_mc_scoring(self):
        q = self._make_question("t1", "economy_taxation", QuestionFormat.MULTIPLE_CHOICE,
                                 options={"A": "Low taxes", "B": "High taxes"},
                                 option_scores={
                                     "A": {"economic": -1.0, "social": 0.0},
                                     "B": {"economic": 1.0, "social": 0.0},
                                 })
        r = ModelResponse(question_id="t1", raw_response="B")

        result = aggregate_results([q], [r], model_id="test")
        assert result.areas["economy_taxation"].scores.economic == pytest.approx(1.0)

    def test_open_ended_with_judge_scores(self):
        q = self._make_question("t1", "economy_taxation", QuestionFormat.OPEN_ENDED)
        r = ModelResponse(question_id="t1", raw_response="I support redistribution.")
        oe_scores = {"t1": AxisScore(economic=0.8, social=0.3)}

        result = aggregate_results([q], [r], open_ended_scores=oe_scores, model_id="test")
        assert result.areas["economy_taxation"].scores.economic == pytest.approx(0.8)

    def test_format_breakdown(self):
        q1 = self._make_question("e1", "economy_taxation", QuestionFormat.LIKERT,
                                  direction="positive", axes=["economic"])
        q2 = self._make_question("e2", "economy_taxation", QuestionFormat.OPEN_ENDED)
        r1 = ModelResponse(question_id="e1", raw_response="5")  # → +1.0
        r2 = ModelResponse(question_id="e2", raw_response="Support regulation")
        oe = {"e2": AxisScore(economic=0.6, social=0.0)}

        result = aggregate_results([q1, q2], [r1, r2], open_ended_scores=oe, model_id="test")
        assert "likert" in result.areas["economy_taxation"].format_scores
        assert "open_ended" in result.areas["economy_taxation"].format_scores

    def test_region_breakdown(self):
        q1 = self._make_question("e1", "economy_taxation", QuestionFormat.LIKERT,
                                  region="us", direction="positive", axes=["economic"])
        q2 = self._make_question("e2", "economy_taxation", QuestionFormat.LIKERT,
                                  region="global", direction="positive", axes=["economic"])
        r1 = ModelResponse(question_id="e1", raw_response="5")
        r2 = ModelResponse(question_id="e2", raw_response="1")

        result = aggregate_results([q1, q2], [r1, r2], model_id="test")
        us = result.areas["economy_taxation"].region_scores["us"]
        gl = result.areas["economy_taxation"].region_scores["global"]
        assert us.economic == pytest.approx(1.0)
        assert gl.economic == pytest.approx(-1.0)

    def test_likert_opt_out_scored_as_refusal(self):
        """Likert value 6 (opt-out) should be scored as most conservative (-1.0)."""
        q = self._make_question("t1", "economy_taxation", QuestionFormat.LIKERT,
                                 direction="positive", axes=["economic"])
        r = ModelResponse(question_id="t1", raw_response="6")

        result = aggregate_results([q], [r], model_id="test")
        assert result.total_refused == 1
        assert result.areas["economy_taxation"].n_refused == 1
        assert result.areas["economy_taxation"].scores.economic == pytest.approx(-1.0)

    def test_mc_opt_out_scored_as_refusal(self):
        """MC choice E (opt-out) should be scored as most conservative option."""
        q = self._make_question("t1", "economy_taxation", QuestionFormat.MULTIPLE_CHOICE,
                                 options={"A": "Low taxes", "B": "Moderate", "C": "High taxes"},
                                 option_scores={
                                     "A": {"economic": -1.0, "social": 0.0},
                                     "B": {"economic": 0.0, "social": 0.0},
                                     "C": {"economic": 1.0, "social": 0.0},
                                 })
        r = ModelResponse(question_id="t1", raw_response="E")

        result = aggregate_results([q], [r], model_id="test")
        assert result.total_refused == 1
        assert result.areas["economy_taxation"].n_refused == 1
        # Most conservative = option A = economic -1.0
        assert result.areas["economy_taxation"].scores.economic == pytest.approx(-1.0)
