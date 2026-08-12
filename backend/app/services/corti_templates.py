"""Corti template registry.

Templates are created once and reused. Corti keys its response by `sectionId`, so
we persist the `sectionId -> our key` map alongside the template id; without it the
generated fields cannot be told apart.

Corti's `outputSchema` supports `string`, `string` with an `enum`, arrays of strings
(with or without an `enum` — both are fine), and `boolean`. **Objects and object
arrays return HTTP 500.** So anything structured is expressed as a fixed set of flat
sections: question generation and scoring use numbered slots rather than one section
returning a list of objects. A list of plain strings needs no slots — competency
extraction returns one free-string array.

Each spec carries a fingerprint of its own prompts. Edit a prompt and the fingerprint
changes, so the next use provisions a fresh template rather than silently generating
against the old wording.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from app.core.constants import Subject
from app.data.axes import ALL_IDS as ALL_AXIS_IDS
from app.data.bloom import AFFECTIVE_LEVELS, COGNITIVE_LEVELS
from app.db import mongo
from app.services.corti import CortiError, corti

logger = logging.getLogger(__name__)

PARSE_TEMPLATE = "elog_parse"
AXIS_TEMPLATE = "axis_suggest"
QUESTION_TEMPLATE = "question_gen"
SCORING_TEMPLATE = "answer_score"
EXTRACT_TEMPLATE = "competency_extract"
PARAMETER_TEMPLATE = "parameter_suggest"

# Default slot count when a spec is built without one. NOT a cap — an exercise
# may hold as many questions as the professor certifies parameters, and the spec
# for any size is built on demand.
MAX_QUESTIONS = 5
# The shortlist the AI proposes. Deliberately smaller than the offered set —
# a suggestion of ten is not a suggestion.
MAX_SUGGESTIONS = 4
# Parameters proposed per axis. A set to prune, not a single line to accept.
MAX_PARAMETERS = 3

OMISSION_KEYS = ["laterality", "consent", "anaesthesia", "indication", "complication", "followup"]
MARK_VALUES = [str(n) for n in range(0, 11)]
VERDICTS = ["correct", "partially correct", "incorrect"]


def _axis_sections() -> list[dict[str, Any]]:
    """The shortlist as ONE array section, not a slot per axis.

    Corti generates each section independently, so a `why_2` section cannot see
    which axis `axis_2` chose — slotting produced rationales attached to the
    wrong axis. An array of enum ids is generated in a single pass and is the
    only shape that stays internally consistent. Per-axis wording comes from the
    closed catalogue instead, and the parameter is the professor's to set (§2A).
    """
    sections: list[dict[str, Any]] = [
        {
            "key": "shortlist",
            "heading": "Suggested axes",
            "prompt": (
                "Choose the three or four axes most worth putting to this resident, "
                "most discriminating first. Use only ids from the ALLOWED AXES list "
                "in the context. Leave out any axis that is merely true of the case "
                "but would not change a decision — that is cosmetic, not "
                "discriminating. Return fewer than three only if the case genuinely "
                "offers fewer."
            ),
            "schema": {
                "type": "array",
                "items": {"type": "string", "enum": ALL_AXIS_IDS},
            },
        },
    ]

    sections.append(
        {
            "key": "critical_axis",
            "heading": "Fatal-error axis",
            "prompt": (
                "Which single axis from the ALLOWED AXES list carries the fatal error "
                "for this case — the mistake that would be disqualifying however well "
                "the rest is answered? Return only its id."
            ),
            "schema": {"type": "string", "enum": ALL_AXIS_IDS},
        }
    )
    sections.append(
        {
            "key": "critical_why",
            "heading": "Why that is fatal",
            "prompt": (
                "Name the specific clinical error that would be disqualifying here, in "
                "at most 25 words. It must be a mistake a resident could actually make "
                "in this case — a missed diagnosis, a dangerous delay, an unsafe "
                "decision. Not a comment about the exercise or the supervision."
            ),
            "schema": {"type": "string"},
        }
    )
    return sections


def _question_sections(slots: int = MAX_QUESTIONS) -> list[dict[str, Any]]:
    """Three flat sections per question slot — Corti cannot return objects.

    Sized to the number of questions actually being asked: Corti generates every
    section in the template, so a fixed five-slot template spent roughly 40% of
    its work writing empty slots for a three-question exercise.
    """
    sections: list[dict[str, Any]] = []
    for slot in range(1, slots + 1):
        sections.append(
            {
                "key": f"q{slot}_prompt",
                "heading": f"Question {slot}",
                "prompt": (
                    f"Write reasoning question {slot}, for the axis listed as SLOT {slot} in "
                    "the context. Vary the logged case along that axis only, keeping every "
                    "other detail of the real case. The question must demand judgement — a "
                    "decision and its justification — not recall of a fact. Address the "
                    "resident directly, one or two sentences. If the context has no SLOT "
                    f"{slot}, return an empty string."
                ),
                "schema": {"type": "string"},
            }
        )
        sections.append(
            {
                "key": f"q{slot}_cognitive",
                "heading": f"Question {slot} cognitive level",
                "prompt": (
                    f"Bloom's cognitive level of question {slot}. Reasoning questions of this "
                    "kind sit at Apply, Analyse or Evaluate; use Remember or Understand only "
                    f"if the question genuinely asks for recall. Empty if there is no SLOT {slot}."
                ),
                "schema": {"type": "string", "enum": COGNITIVE_LEVELS},
            }
        )
        sections.append(
            {
                "key": f"q{slot}_affective",
                "heading": f"Question {slot} affective level",
                "prompt": (
                    f"Krathwohl's affective level of question {slot} — the attitude or "
                    "professional value it puts under test. Empty if there is no SLOT "
                    f"{slot}."
                ),
                "schema": {"type": "string", "enum": AFFECTIVE_LEVELS},
            }
        )
    return sections


def _scoring_sections(slots: int = MAX_QUESTIONS) -> list[dict[str, Any]]:
    """Sized to the number of answers actually being marked — see above."""
    sections: list[dict[str, Any]] = []
    for slot in range(1, slots + 1):
        sections.append(
            {
                "key": f"a{slot}_marks",
                "heading": f"Answer {slot} marks",
                "prompt": (
                    f"Mark the resident's ANSWER {slot} out of 10 against QUESTION {slot}. "
                    "Reward correct reasoning and explicit justification; do not reward "
                    "fluent writing that avoids a decision. Return digits only. Return an "
                    f"empty string if there is no ANSWER {slot}."
                ),
                "schema": {"type": "string", "enum": MARK_VALUES},
            }
        )
        sections.append(
            {
                "key": f"a{slot}_verdict",
                "heading": f"Answer {slot} verdict",
                "prompt": (
                    f"Judge ANSWER {slot}: 'correct' if the reasoning reaches a safe and "
                    "justified decision, 'partially correct' if the decision is right but "
                    "the justification is thin or incomplete, 'incorrect' if the decision "
                    f"is wrong or unsafe. Empty if there is no ANSWER {slot}."
                ),
                "schema": {"type": "string", "enum": VERDICTS},
            }
        )
        sections.append(
            {
                "key": f"a{slot}_feedback",
                "heading": f"Answer {slot} feedback",
                "prompt": (
                    f"One or two sentences of formative feedback on ANSWER {slot}, addressed "
                    "to the resident. Name the specific thing that was missing or wrong, or "
                    "the specific thing that made the reasoning sound. Never generic praise. "
                    f"Empty if there is no ANSWER {slot}."
                ),
                "schema": {"type": "string"},
            }
        )
    return sections


_SPECS: dict[str, dict[str, Any]] = {
    PARSE_TEMPLATE: {
        "name": "opbook360-elog-parse",
        "prompt": (
            "You are reading a postgraduate medical resident's e-logbook entry. "
            "Extract only what the entry actually states. Never infer a fact that is "
            "not written, and never return a value outside an allowed list."
        ),
        "sections": [
            {
                "key": "diagnosis",
                "heading": "Diagnosis",
                "prompt": (
                    "The single primary diagnosis, specimen finding, cause of death or "
                    "topic of this entry, as a concise noun phrase. No full sentence, no "
                    "management detail. If none is stated, return an empty string."
                ),
                "schema": {"type": "string"},
            },
            {
                "key": "procedure",
                "heading": "Procedure",
                "prompt": (
                    "The definitive procedure that was actually carried through, plus the "
                    "implant or technique if stated. Ignore procedures that were only "
                    "attempted, abandoned or unsuccessful. Answer as a short label of at "
                    "most six words, keeping standard abbreviations, in the form "
                    "'ORIF · volar locking plate'. If none, return an empty string."
                ),
                "schema": {"type": "string"},
            },
            {
                "key": "patient_age",
                "heading": "Patient age",
                "prompt": (
                    "The patient's age in years, digits only and nothing else. Return an "
                    "empty string if no age is stated or the entry is not about a patient."
                ),
                "schema": {"type": "string"},
            },
            {
                "key": "patient_sex",
                "heading": "Patient sex",
                "prompt": "The patient's sex. Return 'unknown' if not stated or not applicable.",
                "schema": {"type": "string", "enum": ["Male", "Female", "unknown"]},
            },
            # The competency section is not here: its enum is the professor's own
            # catalogue, so it is appended per subject by `_parse_spec` below.
            {
                "key": "omissions",
                "heading": "Omissions",
                "prompt": (
                    "Which of these are NOT documented anywhere in the entry? laterality "
                    "(which side), consent, anaesthesia, indication (mechanism or reason), "
                    "complication (whether any occurred), followup (the plan afterwards). "
                    "Return only the ones genuinely absent. For an entry that is a topic "
                    "rather than a patient, return an empty list."
                ),
                "schema": {"type": "array", "items": {"type": "string", "enum": OMISSION_KEYS}},
            },
        ],
    },
    AXIS_TEMPLATE: {
        "name": "opbook360-axis-suggest",
        "prompt": (
            "You advise an Indian postgraduate medical professor deciding which "
            "variations of a resident's logged case are worth testing.\n"
            "The context lists the ONLY axes allowed for this case — they are already "
            "filtered by the competency and by what the resident actually did. You may "
            "not name an axis outside that list, and you may not invent one.\n"
            "You are proposing a shortlist, not deciding. Suggest only axes that would "
            "genuinely separate a resident who understands this case from one who does "
            "not; an axis that is merely true of the case but changes no decision is "
            "cosmetic and must be left out."
        ),
        "sections": _axis_sections(),
    },
    QUESTION_TEMPLATE: {
        "name": "opbook360-question-gen",
        "prompt": (
            "You write formative reasoning questions for Indian postgraduate medical "
            "residents, from a case the resident logged themselves.\n"
            "Rules you must not break:\n"
            "1. Vary the case ONLY along the certified axis given for each slot. You may "
            "not introduce a variation of any other kind.\n"
            "2. The resident's role is given. It changes the TYPE of reasoning tested, "
            "never the difficulty: observed asks why the approach was chosen; supervised "
            "removes the senior and asks for the decision; independent asks about "
            "complications, atypical courses and constraints.\n"
            "3. Questions are answered in free text, so never write multiple choice, and "
            "never ask a question answerable by a single word.\n"
            "4. Stay within Indian practice: district hospitals, limited imaging, "
            "restricted implant and ICU availability are realistic constraints."
        ),
        "sections": _question_sections(),
    },
    SCORING_TEMPLATE: {
        "name": "opbook360-answer-score",
        "prompt": (
            "You are an examiner marking an Indian postgraduate medical resident's written "
            "reasoning. The context gives each question, what the question was testing, and "
            "the resident's answer. Mark what the resident actually wrote — never credit "
            "knowledge they did not show. Be fair but not generous: this is formative, so "
            "an inflated mark helps nobody."
        ),
        "sections": _scoring_sections(),
    },
    PARAMETER_TEMPLATE: {
        "name": "opbook360-parameter-suggest",
        "prompt": (
            "You advise an Indian postgraduate medical professor who has chosen ONE "
            "axis — one kind of variation — and now needs concrete ways to vary this "
            "particular case along it.\n"
            "A parameter is the specific change, not the question: 'presenting on day "
            "5 with a walled-off mass', not 'what would you do if...'.\n"
            "Each must be clinically real for THIS case, and each must change what a "
            "competent resident would decide. A variation that is merely true but "
            "changes no decision is cosmetic and must be left out.\n"
            "They must differ from one another in substance, not wording. Return "
            "fewer than three if the case genuinely offers fewer."
        ),
        "sections": [
            {
                "key": "parameters",
                "heading": "Parameters",
                "prompt": (
                    "Give up to three concrete parameters for the axis named in the "
                    "context, each at most 20 words, each a specific variation of this "
                    "case. No numbering, no question marks — just the variation."
                ),
                # A plain string array: proven to work when competency extraction
                # was built, and it needs no numbered slots.
                "schema": {"type": "array", "items": {"type": "string"}},
            }
        ],
    },
    EXTRACT_TEMPLATE: {
        "name": "opbook360-competency-extract",
        "prompt": (
            "You are reading one excerpt from an Indian postgraduate medical "
            "curriculum document and listing the competency statements in it.\n"
            "A competency is something the resident must be able to DO — 'elicit and "
            "present a history of acute abdominal pain', 'interpret an erect abdominal "
            "radiograph'. It is not a unit heading, a topic name, a teaching method, an "
            "assessment method, or a page header.\n"
            "Copy the wording from the document. Do not invent competencies, do not "
            "merge two into one, and do not rewrite them into your own words."
        ),
        # One free-string array, not numbered slots: probed against the live API,
        # and it means an excerpt can return as many competencies as it contains.
        "sections": [
            {
                "key": "competencies",
                "heading": "Competencies",
                "prompt": (
                    "List every competency statement in the excerpt, one per item, in "
                    "the order they appear. Drop the numbering or bullet that precedes "
                    "each one and return the statement itself. If the excerpt contains "
                    "none — it is a contents page, a preface, or a list of textbooks — "
                    "return an empty list rather than inventing something."
                ),
                "schema": {"type": "array", "items": {"type": "string"}},
            }
        ],
    },
}


def _sized(base: str, count: int) -> str:
    """Template key for an exercise of exactly `count` questions.

    Unclamped: an axis may carry as many parameters as the professor wants, and
    each is a question. The spec for any size is built on demand by `_spec_for`.
    """
    return f"{base}_{max(1, count)}"


# --- the parse template, which depends on the professor's catalogue ---------
def parse_template(subject: str) -> str:
    """Template key for parsing an entry in `subject`.

    One template per subject rather than one overall, because the competency enum
    is the subject's own list. A shared template would offer a surgery resident
    every physiology competency and make the choice harder, not easier.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")
    return f"{PARSE_TEMPLATE}:{slug}"


def _competency_section(ids: list[str]) -> dict[str, Any]:
    return {
        "key": "competency",
        "heading": "Competency",
        "prompt": (
            "The context lists the candidate competencies for this subject. Choose "
            "exactly ONE id — the one this entry is the best evidence for. Prefer the "
            "competency the entry actually demonstrates over one it merely mentions. "
            "Return only the id."
        ),
        "schema": {"type": "string", "enum": ids},
    }


async def _parse_spec(key: str) -> dict[str, Any]:
    """The parse spec for one subject: the fixed sections plus its competency enum.

    Read fresh from the catalogue every time. The spec is fingerprinted, so a
    professor editing the catalogue changes the fingerprint and the next parse
    re-provisions against the new list — no separate invalidation to get wrong.
    """
    from app.services import catalogue  # imported here: catalogue imports this module

    base = _SPECS[PARSE_TEMPLATE]
    subject = _SUBJECT_BY_KEY.get(key)
    ids = await catalogue.ids_for(subject) if subject else []

    # An empty enum is not a valid schema, and a subject with no competencies has
    # nothing to choose from anyway — drop the section and let the rules answer.
    sections = base["sections"] + ([_competency_section(ids)] if ids else [])
    return {**base, "name": f"{base['name']}-{key.rpartition(':')[2] or 'all'}", "sections": sections}


_SUBJECT_BY_KEY: dict[str, str] = {parse_template(s.value): s.value for s in Subject}


def _sized_spec(base: str, key: str, sections: Any) -> dict[str, Any]:
    """A question or scoring spec for whatever count the key names."""
    count = max(1, int(key.rpartition("_")[2]))
    return {**_SPECS[base], "name": f"{_SPECS[base]['name']}-{count}", "sections": sections(count)}


async def _spec_for(key: str) -> dict[str, Any]:
    """Static specs by key; the sized and parse specs are built on demand.

    Question and scoring templates used to be pre-registered for counts 1..5,
    which put a hard ceiling on how many questions an exercise could hold. Built
    here instead, any size provisions itself on first use and is then cached in
    Mongo like every other template.
    """
    if key.startswith(f"{PARSE_TEMPLATE}:") or key == PARSE_TEMPLATE:
        return await _parse_spec(key)
    if key.startswith(f"{QUESTION_TEMPLATE}_"):
        return _sized_spec(QUESTION_TEMPLATE, key, _question_sections)
    if key.startswith(f"{SCORING_TEMPLATE}_"):
        return _sized_spec(SCORING_TEMPLATE, key, _scoring_sections)
    return _SPECS[key]


def question_template(count: int) -> str:
    return _sized(QUESTION_TEMPLATE, count)


def scoring_template(count: int) -> str:
    return _sized(SCORING_TEMPLATE, count)


def _fingerprint(spec: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


async def ensure_template(key: str) -> dict[str, Any] | None:
    """Return `{template_id, section_map}` for a spec, provisioning if needed.

    Returns None when Corti is unreachable — callers fall back rather than fail.
    """
    spec = await _spec_for(key)
    fingerprint = _fingerprint(spec)

    cached = await mongo.corti_templates().find_one({"key": key})
    if cached and cached.get("fingerprint") == fingerprint:
        return {"template_id": cached["template_id"], "section_map": cached["section_map"]}

    try:
        section_map: dict[str, str] = {}
        section_ids: list[str] = []
        for section in spec["sections"]:
            section_id = await corti.create_section(
                name=f"{spec['name']}-{section['key']}",
                heading=section["heading"],
                content_prompt=section["prompt"],
                output_schema=section["schema"],
            )
            section_ids.append(section_id)
            section_map[section_id] = section["key"]

        template_id = await corti.create_template(
            name=f"{spec['name']}-{fingerprint}",
            prompt=spec["prompt"],
            section_ids=section_ids,
        )
    except (CortiError, KeyError) as exc:
        logger.warning("Corti template %s unavailable: %s", key, exc)
        if cached:  # a stale template still beats no AI at all
            return {"template_id": cached["template_id"], "section_map": cached["section_map"]}
        return None

    record = {
        "key": key,
        "fingerprint": fingerprint,
        "template_id": template_id,
        "section_map": section_map,
    }
    await mongo.corti_templates().update_one({"key": key}, {"$set": record}, upsert=True)
    logger.info("Provisioned Corti template %s -> %s", key, template_id)
    return {"template_id": template_id, "section_map": section_map}


async def run_template(key: str, context_blocks: list[str]) -> dict[str, Any] | None:
    """Generate against a stored template and return values keyed by our own keys."""
    registry = await ensure_template(key)
    if registry is None:
        return None

    structured = await corti.generate(registry["template_id"], context_blocks)
    section_map: dict[str, str] = registry["section_map"]
    return {
        section_map[section_id]: value
        for section_id, value in structured.items()
        if section_id in section_map and value not in (None, "")
    }


# Re-exported so callers do not need to know the axis module's shape.
__all__ = [
    "ALL_AXIS_IDS",
    "AXIS_TEMPLATE",
    "EXTRACT_TEMPLATE",
    "MAX_PARAMETERS",
    "MAX_QUESTIONS",
    "MAX_SUGGESTIONS",
    "PARAMETER_TEMPLATE",
    "PARSE_TEMPLATE",
    "QUESTION_TEMPLATE",
    "SCORING_TEMPLATE",
    "ensure_template",
    "parse_template",
    "question_template",
    "run_template",
    "scoring_template",
]
