from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser
from app.core.constants import Subject, role_labels
from app.data import bloom
from app.data.axes import AXES, FAMILY_LABELS, Family, subject_class
from app.schemas.entry import CompetencyOut
from app.services import catalogue

router = APIRouter(tags=["meta"])


@router.get("/subjects")
async def list_subjects(user: CurrentUser) -> list[dict[str, Any]]:
    """Each subject with its class, how many competencies it has, and its roles.

    The count rather than the competencies themselves: a loaded curriculum runs to
    dozens per subject, and this response is fetched once and held for the session.
    The entry screen asks for one subject's list when it needs it.
    """
    counts = await catalogue.count_by_subject()
    out: list[dict[str, Any]] = []
    for subject in Subject:
        klass = subject_class(subject.value)
        out.append(
            {
                "value": subject.value,
                "subject_class": klass,
                "competency_count": counts.get(subject.value, 0),
                "roles": [
                    {"value": role.value, "label": label, "hint": hint}
                    for role, (label, hint) in role_labels(klass).items()
                ],
            }
        )
    return out


@router.get("/competencies", response_model=list[CompetencyOut])
async def list_competencies(
    user: CurrentUser,
    subject: Annotated[Subject | None, Query()] = None,
) -> list[dict[str, str]]:
    """The competency spine, for one subject or all of them."""
    if subject is not None:
        return await catalogue.list_for(subject.value)
    items: list[dict[str, str]] = []
    for value in Subject:
        items.extend(await catalogue.list_for(value.value))
    return items


@router.get("/axes")
async def list_axes(user: CurrentUser) -> list[dict[str, Any]]:
    """The complete closed axis list (§2A), grouped into its five families."""
    grouped: list[dict[str, Any]] = []
    for family in Family:
        label, description = FAMILY_LABELS[family]
        grouped.append(
            {
                "id": family.value,
                "label": label,
                "description": description,
                "axes": [axis for axis in AXES if axis["family"] == family],
            }
        )
    return grouped


@router.get("/domains")
async def list_domains(user: CurrentUser) -> dict[str, Any]:
    """The three domains of learning and their levels (§3)."""
    return {
        "cognitive": {
            "label": "Cognitive (COG) — thinking",
            "levels": bloom.describe(bloom.COGNITIVE),
            "target": list(bloom.COGNITIVE_TARGET),
        },
        "affective": {
            "label": "Affective (AFF) — attitudes and values",
            "levels": bloom.describe(bloom.AFFECTIVE),
        },
        "psychomotor": {
            "label": "Psychomotor (PSY) — doing",
            "levels": bloom.describe(bloom.PSYCHOMOTOR),
            "note": (
                "Assessed on real patients in the logbook, not by the reasoning engine."
            ),
        },
    }
