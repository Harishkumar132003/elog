"""Rule-based clinical narrative parser.

Narratives are short and this runs on every typing pause, so the whole pipeline
is regex/set lookups over a single normalisation pass — no model, no I/O.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.lexicon import (
    ATTEMPT_MARKERS,
    CLAUSE_NOISE,
    DEVICE_HEADS,
    DIAGNOSIS_HEADS,
    GENERIC_PROCEDURES,
    LATERALITY,
    OMISSION_CHECKS,
    PHRASE_STOPS,
    PROCEDURES,
    QUALIFIER_PHRASES,
    SITE_TOKENS,
)

_NON_WORD = re.compile(r"[^a-z0-9]+")
_CLAUSE_SPLIT = re.compile(r"[.;\n,]")

# Compact / verbose ways a trainee writes the demographic stem.
_PATIENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?P<age>\d{1,3})\s*(?:yrs?|years?|y/?o|y)?\s*[-/ ]?\s*(?P<sex>[MF])\b"),
    re.compile(r"\b(?P<sex>[MF])\s*[-/]\s*(?P<age>\d{1,3})\b"),
    re.compile(
        r"\b(?P<age>\d{1,3})[\s-]*(?:year|yr)s?[\s-]*old\s+(?P<sex>male|female|man|woman|boy|girl)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<sex>male|female|man|woman|boy|girl)\b[^.]{0,12}?\b(?P<age>\d{1,3})\s*(?:yrs?|years?)\b",
        re.IGNORECASE,
    ),
)

_SEX_MAP = {
    "m": "Male", "male": "Male", "man": "Male", "boy": "Male",
    "f": "Female", "female": "Female", "woman": "Female", "girl": "Female",
}

_QUALIFIER_DISPLAY = {
    "intra articular": "intra-articular",
    "extra articular": "extra-articular",
}

# Longest-first so "open reduction internal fixation" wins over "open reduction".
_PROCEDURE_ALIASES: tuple[tuple[str, str], ...] = tuple(
    sorted(PROCEDURES.items(), key=lambda kv: -len(kv[0]))
)
_QUALIFIERS_BY_LENGTH: tuple[str, ...] = tuple(
    sorted(QUALIFIER_PHRASES, key=len, reverse=True)
)


def normalise(text: str) -> str:
    """Lowercase, strip punctuation/hyphens, collapse whitespace."""
    return _NON_WORD.sub(" ", text.lower()).strip()


def _clauses(text: str) -> list[list[str]]:
    """Split into clause token lists, dropping empties."""
    out: list[list[str]] = []
    for raw in _CLAUSE_SPLIT.split(text):
        tokens = normalise(raw).split()
        if tokens:
            out.append(tokens)
    return out


def _extract_patient(text: str) -> dict[str, Any] | None:
    for pattern in _PATIENT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        age = int(match.group("age"))
        if not 0 < age <= 120:
            continue
        sex = _SEX_MAP.get(match.group("sex").lower())
        return {"age": age, "sex": sex, "display": f"{age} · {sex}" if sex else str(age)}
    return None


def _extract_qualifiers(tokens: list[str]) -> list[str]:
    """Descriptors present in the diagnosis clause, in reading order."""
    clause = " ".join(tokens)
    found: list[tuple[int, str]] = []
    consumed: list[tuple[int, int]] = []
    for phrase in _QUALIFIERS_BY_LENGTH:
        start = clause.find(phrase)
        while start != -1:
            end = start + len(phrase)
            on_boundary = (start == 0 or clause[start - 1] == " ") and (
                end == len(clause) or clause[end] == " "
            )
            if on_boundary and not any(s < end and start < e for s, e in consumed):
                consumed.append((start, end))
                found.append((start, _QUALIFIER_DISPLAY.get(phrase, phrase)))
                break
            start = clause.find(phrase, start + 1)
    found.sort()
    return [label for _, label in found]


def _extract_diagnosis(clauses: list[list[str]]) -> dict[str, Any] | None:
    for tokens in clauses:
        head_index = next(
            (i for i, token in enumerate(tokens) if token in DIAGNOSIS_HEADS), None
        )
        if head_index is None:
            continue

        # Walk left while the token still names a site/region, not a descriptor.
        start = head_index
        while start > 0 and tokens[start - 1] in SITE_TOKENS:
            start -= 1
        core_tokens = [t for t in tokens[start : head_index + 1] if t not in CLAUSE_NOISE]
        if not core_tokens:
            continue

        core = " ".join(core_tokens)
        core = core[0].upper() + core[1:]
        qualifiers = [q for q in _extract_qualifiers(tokens) if q not in core_tokens]
        display = f"{core} ({', '.join(qualifiers)})" if qualifiers else core
        return {"core": core, "qualifiers": qualifiers, "display": display}
    return None


def _device_phrase(tokens: list[str]) -> str | None:
    """Recover an implant/hardware phrase such as `volar locking plate`."""
    for i in range(len(tokens) - 1, -1, -1):
        if tokens[i] not in DEVICE_HEADS:
            continue
        start = i
        while (
            start > 0
            and i - start < 3
            and tokens[start - 1] not in PHRASE_STOPS
            and tokens[start - 1] not in DEVICE_HEADS
            and tokens[start - 1] not in PROCEDURES
        ):
            start -= 1
        return " ".join(tokens[start : i + 1])
    return None


def _extract_procedures(clauses: list[list[str]]) -> dict[str, Any] | None:
    hits: list[dict[str, Any]] = []
    for index, tokens in enumerate(clauses):
        clause = " ".join(tokens)
        attempted = any(marker in clause for marker in ATTEMPT_MARKERS)
        consumed: list[tuple[int, int]] = []
        for alias, label in _PROCEDURE_ALIASES:
            position = clause.find(alias)
            while position != -1:
                end = position + len(alias)
                on_boundary = (position == 0 or clause[position - 1] == " ") and (
                    end == len(clause) or clause[end] == " "
                )
                if on_boundary and not any(s < end and position < e for s, e in consumed):
                    consumed.append((position, end))
                    hits.append(
                        {
                            "label": label,
                            "attempted": attempted,
                            "rank": 0 if alias in GENERIC_PROCEDURES else 1,
                            "clause": index,
                            "order": (index, position),
                        }
                    )
                    break
                position = clause.find(alias, position + 1)

    if not hits:
        return None

    hits.sort(key=lambda hit: hit["order"])
    # The definitive procedure is the most specific one actually carried through —
    # not merely the last mentioned, which is often a generic restatement.
    definitive = max(
        hits,
        key=lambda hit: (not hit["attempted"], hit["rank"], hit["order"]),
    )

    detail = _device_phrase(clauses[definitive["clause"]]) or next(
        (_device_phrase(tokens) for tokens in clauses if _device_phrase(tokens)), None
    )
    # A generic term only earns a mention when nothing more specific beat it.
    others = [
        {"name": hit["label"], "attempted": hit["attempted"]}
        for hit in hits
        if hit is not definitive
        and hit["label"] != definitive["label"]
        and hit["rank"] >= definitive["rank"]
    ]
    return {
        "name": definitive["label"],
        "detail": detail,
        "display": f"{definitive['label']} · {detail}" if detail else definitive["label"],
        "steps": others,
    }


def _omissions(normalised: str) -> list[dict[str, str]]:
    padded = f" {normalised} "
    missing: list[dict[str, str]] = []
    for key, short, label, phrases in OMISSION_CHECKS:
        if not any(f" {phrase} " in padded for phrase in phrases):
            missing.append({"id": key, "short": short, "label": label})
    return missing


def parse_narrative(text: str) -> dict[str, Any]:
    """Derive structured facts from a free-text logbook entry."""
    normalised = normalise(text)
    if not normalised:
        return {
            "diagnosis": None,
            "procedure": None,
            "patient": None,
            "laterality": None,
            "omissions": [],
            "normalised": "",
        }

    clauses = _clauses(text)
    tokens = set(normalised.split())
    return {
        "diagnosis": _extract_diagnosis(clauses),
        "procedure": _extract_procedures(clauses),
        "patient": _extract_patient(text),
        "laterality": next((side for side in LATERALITY if side in tokens), None),
        "omissions": _omissions(normalised),
        "normalised": normalised,
    }
