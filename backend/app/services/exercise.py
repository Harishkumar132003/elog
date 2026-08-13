"""Screen 4 · question generation.

The professor's certification decides *what* is asked: one question per parameter
they certified, with exactly one carrying the Critical flag. An axis may hold
several parameters — it is a *kind* of variation, and a case is often worth
testing along it more than one way — so the unit here is a slot, not an axis.
Corti writes the questions; it can only vary the case along axes it was handed, so
it cannot invent one.

When Corti is unavailable the axis's own "what it varies" line drives a scripted
question, so a demo never dead-ends (§5.1).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import get_settings
from app.core.constants import DopsRole, role_labels
from app.data.axes import BY_ID as AXIS_BY_ID
from app.data.axes import subject_class
from app.data.bloom import DEFAULT_MARKS, PSYCHOMOTOR_ASSESSABLE
from app.services.corti import CortiError
from app.services.corti_templates import question_template, run_template

logger = logging.getLogger(__name__)
_settings = get_settings()

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
    DopsRole.SUPERVISOR: (
        "This person supervised someone else doing it. Test the oversight decision — "
        "when to intervene, what was safe to delegate, and what they were watching "
        "for. Not their own hands-on technique."
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

# Psychomotor follows the ROLE, not the axis: what someone's hands were doing is
# a fact about their part in the case, and the axis only changes what is asked
# about it. Capped at the three preparatory levels — see PSYCHOMOTOR_ASSESSABLE.
_FALLBACK_PSYCHOMOTOR: dict[str, str] = {
    DopsRole.OBSERVED: "Perception",       # watching, and reading the patient
    DopsRole.SUPERVISED: "Guided response",  # doing it under direction
    DopsRole.INDEPENDENT: "Guided response",
    DopsRole.SUPERVISOR: "Set",            # readiness — knowing when to step in
    DopsRole.TOPIC: "Perception",
}


def _role_of(entry: dict[str, Any]) -> DopsRole:
    return DopsRole(entry["role"]) if entry.get("role") in set(DopsRole) else DopsRole.SUPERVISED


def default_psychomotor(entry: dict[str, Any]) -> str:
    return _FALLBACK_PSYCHOMOTOR.get(_role_of(entry), "Perception")


def default_levels(axis_id: str) -> tuple[str, str]:
    """The cognitive and affective levels an axis lands on when nothing says otherwise.

    Used for a question the professor wrote or reworded themselves — the levels
    are a property of the kind of variation being tested, so the axis can supply
    them without asking the AI again.
    """
    axis = AXIS_BY_ID.get(axis_id) or {}
    family = str(axis.get("family", ""))
    return (
        _FALLBACK_COGNITIVE.get(family, "Apply"),
        _FALLBACK_AFFECTIVE.get(family, "Responding"),
    )


def certified_slots(certification: dict[str, Any]) -> list[dict[str, Any]]:
    """One slot per parameter, flattened, in the professor's own order.

    An axis is a *kind* of variation, so it can carry several parameters worth
    testing — each becomes its own question. There is no cap: a professor who
    wants nine questions gets nine.

    Reads both shapes. A certification written before parameters were a list has
    a flat `parameter` / `marks` / `critical` on the axis, and yields exactly the
    one slot it always did — so old cases keep generating what they generated.
    """
    slots: list[dict[str, Any]] = []
    for axis in certification.get("axes", []):
        if not axis.get("discriminates"):
            continue
        parameters = axis.get("parameters")
        if not parameters:
            parameters = [
                {
                    "text": axis.get("parameter", ""),
                    "marks": axis.get("marks", DEFAULT_MARKS),
                    "critical": axis.get("critical", False),
                }
            ]
        for parameter in parameters:
            slots.append({"axis_id": axis["axis_id"], **parameter})
    return slots


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
        f"This person's role: {role_label}",
        f"Diagnosis: {(parsed.get('diagnosis') or {}).get('display') or '—'}",
        f"Procedure: {(parsed.get('procedure') or {}).get('display') or '—'}",
        f"Patient: {(parsed.get('patient') or {}).get('display') or 'not a patient case'}",
    ]

    # A case worked by several people carries the shared account as well as this
    # participant's own. Both matter: the shared half is what actually happened,
    # their own half is what they saw of it and is what the questions must test.
    shared = (entry.get("case_narrative") or "").strip()
    if shared:
        lines += ["", "WHAT HAPPENED (shared by everyone who was there):", shared]
        lines += ["", f"WHAT THIS {role_label.upper()} WROTE:", entry.get("narrative", "")]
    else:
        lines += ["", "The resident wrote:", entry.get("narrative", "")]

    lines += ["", _ROLE_BRIEF.get(role, "")]
    return "\n".join(lines)


def _axis_context(slots: list[dict[str, Any]]) -> str:
    """One SLOT per parameter.

    Two slots can share an axis — the professor may want the same kind of
    variation tested several ways — so the instruction is explicit that they must
    not come out as the same question with different words.
    """
    lines = [
        "CERTIFIED VARIATIONS — one question per slot, varying only along that "
        "slot's axis and its parameter.",
        "Slots may repeat an axis with a different parameter. When they do, the "
        "questions must be genuinely different, not the same question reworded.",
    ]
    for index, slot in enumerate(slots, start=1):
        axis = AXIS_BY_ID.get(slot["axis_id"])
        if axis is None:
            continue
        parts = [f"SLOT {index}: {axis['label']} — {axis['varies']}"]
        if slot.get("text"):
            parts.append(f"Professor's parameter: {slot['text']}")
        if slot.get("critical"):
            parts.append(
                "THIS IS THE CRITICAL ITEM — the fatal error for this case. Write the "
                "question so that a wrong answer is a disqualifying reasoning failure."
            )
        lines.append("  ".join(parts))
    return "\n".join(lines)


def _scripted(slots: list[dict[str, Any]], entry: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Deterministic questions, used only when Corti cannot be reached.

    Keyed by slot position, not by axis id: two slots can share an axis, and a
    dict keyed on the axis would silently collapse them into one question.
    """
    parsed = entry.get("parsed") or {}
    subject_line = (parsed.get("diagnosis") or {}).get("core") or "this case"
    questions: dict[int, dict[str, Any]] = {}

    for index, slot in enumerate(slots, start=1):
        axis = AXIS_BY_ID.get(slot["axis_id"])
        if axis is None:
            continue
        parameter = slot.get("text") or axis["example"]
        questions[index] = {
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
            "psychomotor": default_psychomotor(entry),
            "marks": int(slot.get("marks") or DEFAULT_MARKS),
            "critical": bool(slot.get("critical")),
        }
    return questions


async def generate_questions(
    entry: dict[str, Any], certification: dict[str, Any]
) -> dict[str, Any]:
    """One question per certified parameter, tagged across the three domains."""
    slots = certified_slots(certification)
    if not slots:
        return {"questions": [], "source": "none"}

    try:
        # A template sized to exactly this many questions — no empty slots.
        fields = await run_template(
            question_template(len(slots)), [case_context(entry), _axis_context(slots)]
        )
    except CortiError as exc:
        logger.warning("Corti question generation unavailable: %s", exc)
        fields = None
    except Exception:
        logger.exception("Unexpected error generating questions")
        fields = None

    scripted = _scripted(slots, entry)
    if not fields:
        return {"questions": list(scripted.values()), "source": "rules-fallback"}

    questions: dict[int, dict[str, Any]] = {}
    for index, slot in enumerate(slots, start=1):
        axis = AXIS_BY_ID.get(slot["axis_id"])
        prompt = str(fields.get(f"q{index}_prompt") or "").strip()
        if axis is None or not prompt:
            continue
        family = str(axis["family"])
        questions[index] = {
            "id": index,
            "axis_id": axis["id"],
            "axis_label": axis["label"],
            "prompt": prompt,
            "cognitive": fields.get(f"q{index}_cognitive")
            or _FALLBACK_COGNITIVE.get(family, "Apply"),
            "affective": fields.get(f"q{index}_affective")
            or _FALLBACK_AFFECTIVE.get(family, "Responding"),
            # §3.3 caps this at the preparatory levels: performed skill is judged
            # on a real patient, not from an answer. Anything outside the three
            # falls back to what the role implies.
            "psychomotor": fields.get(f"q{index}_psychomotor")
            if fields.get(f"q{index}_psychomotor") in PSYCHOMOTOR_ASSESSABLE
            else default_psychomotor(entry),
            "marks": int(slot.get("marks") or DEFAULT_MARKS),
            "critical": bool(slot.get("critical")),
        }

    # A partial generation is worse than a scripted set the resident can actually
    # answer, so any slot Corti skipped falls back to its scripted twin. Keyed on
    # slot position throughout: two slots may share an axis, and keying on the
    # axis would drop the second one.
    for index, question in scripted.items():
        questions.setdefault(index, question)

    ordered = [questions[index] for index in sorted(questions)]
    for position, question in enumerate(ordered, start=1):
        question["id"] = position

    return {"questions": ordered, "source": _settings.ai_provider}


async def generate_one(
    entry: dict[str, Any], axis_id: str, parameter: str, marks: int, critical: bool
) -> dict[str, Any] | None:
    """One question, for the professor building a set a card at a time.

    Same generator as the batch path, handed a one-slot certification — so it
    uses `question_gen_1`, an already-provisioned template, and keeps the same
    scripted fallback when Corti cannot be reached.

    Wrapped in a ceiling because this blocks a request rather than streaming.
    Cloudflare cuts an idle connection at 100s and our Corti HTTP timeout is
    longer than that, so without this a hung call would become a 524 while the
    server waited on. Timing out here returns the scripted question instead,
    which the professor can reword — a worse question, but a live screen.
    """
    certification = {
        "axes": [
            {
                "axis_id": axis_id,
                "discriminates": True,
                "parameters": [{"text": parameter, "marks": marks, "critical": critical}],
            }
        ]
    }

    try:
        async with asyncio.timeout(_settings.question_timeout_seconds):
            generated = await generate_questions(entry, certification)
    except TimeoutError:
        logger.warning(
            "Corti took longer than %ss writing one question; using the scripted one",
            _settings.question_timeout_seconds,
        )
        slots = certified_slots(certification)
        scripted = _scripted(slots, entry)
        generated = {"questions": list(scripted.values()), "source": "rules-fallback"}

    questions = generated.get("questions") or []
    if not questions:
        return None
    return {**questions[0], "source": generated.get("source", _settings.ai_provider)}
