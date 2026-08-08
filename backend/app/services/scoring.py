"""Screen 4 · marking, and the roll-up (specification §3).

Each answer earns a mark and carries its three domain tags. The Critical flag is
scored separately and as pass/fail: "A wrong answer to a Critical question is a
disqualifying reasoning failure regardless of the rest of the score."
"""

from __future__ import annotations

import logging
from typing import Any

from app.data.bloom import COGNITIVE_LEVELS
from app.services.corti import CortiError
from app.services.corti_templates import MAX_QUESTIONS, run_template, scoring_template

logger = logging.getLogger(__name__)

# A Critical item is failed by a wrong answer, per §3.4.
_FAILING_VERDICTS = {"incorrect"}


def _answer_context(questions: list[dict[str, Any]], answers: dict[int, str]) -> str:
    blocks: list[str] = []
    for question in questions[:MAX_QUESTIONS]:
        slot = question["id"]
        blocks.append(
            "\n".join(
                [
                    f"QUESTION {slot} (testing: {question['axis_label']}; "
                    f"cognitive level {question['cognitive']}; out of {question['marks']}"
                    + ("; CRITICAL ITEM" if question["critical"] else "")
                    + ")",
                    question["prompt"],
                    "",
                    f"ANSWER {slot}",
                    answers.get(slot, "").strip() or "(the resident left this blank)",
                    "",
                ]
            )
        )
    return "\n".join(blocks)


def _unscored(questions: list[dict[str, Any]], answers: dict[int, str]) -> list[dict[str, Any]]:
    """Fallback marking when Corti is unreachable.

    Deliberately crude and clearly labelled: it records that an answer was given
    and keeps the loop moving, rather than inventing a credible-looking mark.
    """
    results: list[dict[str, Any]] = []
    for question in questions:
        answer = (answers.get(question["id"]) or "").strip()
        substantive = len(answer.split()) >= 25
        results.append(
            {
                **_tags(question),
                "marks_awarded": 0,
                "verdict": "not scored",
                "feedback": (
                    "Your answer was recorded but could not be marked automatically — "
                    "the marking service was unavailable."
                    if substantive
                    else "Too brief to mark. A reasoning answer needs a decision and its "
                    "justification."
                ),
                "critical_failed": False,
            }
        )
    return results


def _tags(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_id": question["id"],
        "axis_id": question["axis_id"],
        "axis_label": question["axis_label"],
        "prompt": question["prompt"],
        "cognitive": question["cognitive"],
        "affective": question["affective"],
        "psychomotor": question["psychomotor"],
        "marks": question["marks"],
        "critical": question["critical"],
    }


def _roll_up(results: list[dict[str, Any]], scored: bool) -> dict[str, Any]:
    """Per-question scores aggregate to a per-competency result (§3.5)."""
    total = sum(item["marks_awarded"] for item in results)
    available = sum(item["marks"] for item in results)
    critical_failed = any(item["critical_failed"] for item in results)
    percentage = round(100 * total / available) if available else 0

    # The highest cognitive level the resident actually reached on a correct answer.
    reached = [
        item["cognitive"]
        for item in results
        if item["verdict"] == "correct" and item["cognitive"] in COGNITIVE_LEVELS
    ]
    highest = max(reached, key=COGNITIVE_LEVELS.index) if reached else None

    if not scored:
        outcome = "Not scored"
    elif critical_failed:
        # Independent of the marks — that is the whole point of the flag.
        outcome = "Critical failure"
    elif percentage >= 70:
        outcome = "Satisfactory"
    elif percentage >= 50:
        outcome = "Borderline"
    else:
        outcome = "Unsatisfactory"

    return {
        "marks_awarded": total,
        "marks_available": available,
        "percentage": percentage,
        "critical_failed": critical_failed,
        "highest_cognitive": highest,
        "outcome": outcome,
    }


def pending_summary() -> dict[str, Any]:
    """Placeholder roll-up for an attempt whose marking has not finished."""
    return _roll_up([], scored=False)


async def score_answers(
    questions: list[dict[str, Any]], answers: dict[int, str]
) -> dict[str, Any]:
    """Mark every answer and roll the result up to the competency."""
    if not questions:
        return {"results": [], "summary": _roll_up([], False), "source": "none"}

    try:
        fields = await run_template(
            scoring_template(len(questions)), [_answer_context(questions, answers)]
        )
    except CortiError as exc:
        logger.warning("Corti marking unavailable: %s", exc)
        fields = None
    except Exception:
        logger.exception("Unexpected error marking answers")
        fields = None

    if not fields:
        results = _unscored(questions, answers)
        return {"results": results, "summary": _roll_up(results, False), "source": "rules-fallback"}

    results: list[dict[str, Any]] = []
    for question in questions:
        slot = question["id"]
        raw_marks = str(fields.get(f"a{slot}_marks") or "").strip()
        awarded = int(raw_marks) if raw_marks.isdigit() else 0
        awarded = min(awarded, question["marks"])
        verdict = fields.get(f"a{slot}_verdict") or "not scored"
        blank = not (answers.get(slot) or "").strip()

        results.append(
            {
                **_tags(question),
                "marks_awarded": 0 if blank else awarded,
                "verdict": "incorrect" if blank else verdict,
                "feedback": fields.get(f"a{slot}_feedback")
                or ("No answer was given." if blank else ""),
                "critical_failed": bool(question["critical"])
                and (blank or verdict in _FAILING_VERDICTS),
            }
        )

    return {"results": results, "summary": _roll_up(results, True), "source": "corti"}
