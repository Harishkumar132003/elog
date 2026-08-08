"""Screen 4 · question generation.

The professor's certification decides *what* is asked: one question per axis they
marked as discriminating, with the fatal-error axis carrying the Critical flag.
Corti writes the questions; it can only vary the case along axes it was handed, so
it cannot invent one.

When Corti is unavailable the axis's own "what it varies" line drives a scripted
question, so a demo never dead-ends (§5.1).
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.constants import DopsRole, role_labels
from app.data.axes import BY_ID as AXIS_BY_ID
from app.data.axes import subject_class
from app.data.bloom import DEFAULT_MARKS, PSYCHOMOTOR_NOT_ASSESSED
from app.services.corti import CortiError
from app.services.corti_templates import MAX_QUESTIONS, question_template, run_template

logger = logging.getLogger(__name__)

# §2 — the role changes the type of reasoning, never the difficulty.
_ROLE_BRIEF: dict[str, str] = {
    DopsRole.OBSERVED: (
        "The resident watched this being done. Test comprehension: why this approach "
        "was chosen and what would have changed it."
    ),
    DopsRole.SUPERVISED: (
        "The resident did this with a senior present. Test decision-making with the "
        "safety net removed."
    ),
    DopsRole.INDEPENDENT: (
        "The resident did this unsupervised. Test the edges: complications, atypical "
        "courses and constraints."
    ),
    DopsRole.TOPIC: (
        "This is a topic, not a patient. Test the concept itself and its applied "
        "clinical link."
    ),
}

# Cognitive level a scripted question lands on, by axis family.
_FALLBACK_COGNITIVE = {
    "patient": "Apply",
    "presentation": "Analyse",
    "context": "Evaluate",
    "course": "Evaluate",
    "uncertainty": "Analyse",
    "concept": "Apply",
}
_FALLBACK_AFFECTIVE = {
    "patient": "Responding",
    "presentation": "Receiving",
    "context": "Valuing",
    "course": "Responding",
    "uncertainty": "Valuing",
    "concept": "Receiving",
}


def certified_axes(certification: dict[str, Any]) -> list[dict[str, Any]]:
    """Only axes the professor marked as discriminating become questions."""
    chosen = [axis for axis in certification.get("axes", []) if axis.get("discriminates")]
    return chosen[:MAX_QUESTIONS]


def case_context(entry: dict[str, Any]) -> str:
    parsed = entry.get("parsed") or {}
    subject = entry["subject"]
    labels = role_labels(subject_class(subject))
    role = DopsRole(entry["role"]) if entry.get("role") in set(DopsRole) else DopsRole.SUPERVISED
    role_label = labels.get(role, ("", ""))[0] or role.value

    lines = [
        "THE LOGGED CASE",
        f"Subject: {subject}",
        f"Competency: {entry.get('competency_title') or '—'}",
        f"Resident's role: {role_label}",
        f"Diagnosis: {(parsed.get('diagnosis') or {}).get('display') or '—'}",
        f"Procedure: {(parsed.get('procedure') or {}).get('display') or '—'}",
        f"Patient: {(parsed.get('patient') or {}).get('display') or 'not a patient case'}",
        "",
        "The resident wrote:",
        entry.get("narrative", ""),
        "",
        _ROLE_BRIEF.get(role, ""),
    ]
    return "\n".join(lines)


def _axis_context(axes: list[dict[str, Any]]) -> str:
    lines = ["CERTIFIED AXES — one question per slot, varying only along that axis."]
    for index, entry in enumerate(axes, start=1):
        axis = AXIS_BY_ID.get(entry["axis_id"])
        if axis is None:
            continue
        parts = [f"SLOT {index}: {axis['label']} — {axis['varies']}"]
        if entry.get("parameter"):
            parts.append(f"Professor's parameter: {entry['parameter']}")
        if entry.get("critical"):
            parts.append(
                "THIS IS THE CRITICAL ITEM — the fatal error for this case. Write the "
                "question so that a wrong answer is a disqualifying reasoning failure."
            )
        lines.append("  ".join(parts))
    return "\n".join(lines)


def _scripted(axes: list[dict[str, Any]], entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic questions, used only when Corti cannot be reached."""
    parsed = entry.get("parsed") or {}
    subject_line = (parsed.get("diagnosis") or {}).get("core") or "this case"
    questions: list[dict[str, Any]] = []

    for index, chosen in enumerate(axes, start=1):
        axis = AXIS_BY_ID.get(chosen["axis_id"])
        if axis is None:
            continue
        parameter = chosen.get("parameter") or axis["example"]
        questions.append(
            {
                "id": index,
                "axis_id": axis["id"],
                "axis_label": axis["label"],
                "prompt": (
                    f"Same case of {subject_line.lower()}, but {axis['varies'].lower()} "
                    f"({parameter}). What is your management now, and what makes it "
                    "the right call?"
                ),
                "cognitive": _FALLBACK_COGNITIVE.get(str(axis["family"]), "Apply"),
                "affective": _FALLBACK_AFFECTIVE.get(str(axis["family"]), "Responding"),
                "psychomotor": PSYCHOMOTOR_NOT_ASSESSED,
                "marks": int(chosen.get("marks") or DEFAULT_MARKS),
                "critical": bool(chosen.get("critical")),
            }
        )
    return questions


async def generate_questions(
    entry: dict[str, Any], certification: dict[str, Any]
) -> dict[str, Any]:
    """One question per certified axis, tagged across the three domains."""
    axes = certified_axes(certification)
    if not axes:
        return {"questions": [], "source": "none"}

    try:
        # A template sized to exactly this many questions — no empty slots.
        fields = await run_template(
            question_template(len(axes)), [case_context(entry), _axis_context(axes)]
        )
    except CortiError as exc:
        logger.warning("Corti question generation unavailable: %s", exc)
        fields = None
    except Exception:
        logger.exception("Unexpected error generating questions")
        fields = None

    if not fields:
        return {"questions": _scripted(axes, entry), "source": "rules-fallback"}

    questions: list[dict[str, Any]] = []
    for index, chosen in enumerate(axes, start=1):
        axis = AXIS_BY_ID.get(chosen["axis_id"])
        prompt = str(fields.get(f"q{index}_prompt") or "").strip()
        if axis is None or not prompt:
            continue
        family = str(axis["family"])
        questions.append(
            {
                "id": index,
                "axis_id": axis["id"],
                "axis_label": axis["label"],
                "prompt": prompt,
                "cognitive": fields.get(f"q{index}_cognitive")
                or _FALLBACK_COGNITIVE.get(family, "Apply"),
                "affective": fields.get(f"q{index}_affective")
                or _FALLBACK_AFFECTIVE.get(family, "Responding"),
                # §3.3 — psychomotor is assessed on real patients, not by this engine.
                "psychomotor": PSYCHOMOTOR_NOT_ASSESSED,
                "marks": int(chosen.get("marks") or DEFAULT_MARKS),
                "critical": bool(chosen.get("critical")),
            }
        )

    # A partial generation is worse than a scripted set the resident can actually answer.
    if len(questions) < len(axes):
        scripted = {q["axis_id"]: q for q in _scripted(axes, entry)}
        have = {q["axis_id"] for q in questions}
        questions += [q for axis_id, q in scripted.items() if axis_id not in have]
        questions.sort(key=lambda q: [a["axis_id"] for a in axes].index(q["axis_id"]))
        for position, question in enumerate(questions, start=1):
            question["id"] = position

    return {"questions": questions, "source": "corti" if fields else "rules-fallback"}
