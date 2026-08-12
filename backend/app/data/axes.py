"""The closed set of variation axes (specification §2A).

"This is the closed set of variation axes. The system offers only these; a
professor prunes them per entity, and new axes are added centrally, never
invented live."

Sixteen clinical axes in five families, plus the four concept-variation axes that
replace the patient-factor and context families for pre-clinical subjects. No axis
outside this file may ever reach a professor or the question generator.
"""

from enum import StrEnum

from app.core.constants import DopsRole, Subject


class Family(StrEnum):
    PATIENT = "patient"
    PRESENTATION = "presentation"
    CONTEXT = "context"
    COURSE = "course"
    UNCERTAINTY = "uncertainty"
    CONCEPT = "concept"


FAMILY_LABELS: dict[Family, tuple[str, str]] = {
    Family.PATIENT: (
        "Patient-factor",
        "The patient's physiology changes, so the correct answer may change.",
    ),
    Family.PRESENTATION: ("Presentation", "How and when the patient presents."),
    Family.CONTEXT: (
        "Context",
        "The setting constrains what is possible.",
    ),
    Family.COURSE: ("Course", "What happens after the initial decision."),
    Family.UNCERTAINTY: ("Diagnostic uncertainty", "The diagnosis itself is not clean."),
    Family.CONCEPT: (
        "Concept variation",
        "For pre-clinical subjects, replacing the patient-factor and context families.",
    ),
}

# id, family, label, what it varies, example — verbatim from §2A.
AXES: tuple[dict[str, str], ...] = (
    # --- §2A.1 Patient-factor -------------------------------------------
    {
        "id": "comorbidity",
        "family": Family.PATIENT,
        "label": "Comorbidity",
        "varies": "A coexisting condition that alters management or risk",
        "example": "Diabetes, immunosuppression, cardiac or renal impairment, coagulopathy",
    },
    {
        "id": "age-extreme",
        "family": Family.PATIENT,
        "label": "Age extreme",
        "varies": "Patient at the young or old end of the range",
        "example": "Paediatric presentation; frail elderly",
    },
    {
        "id": "physiological-state",
        "family": Family.PATIENT,
        "label": "Physiological state",
        "varies": "Stable → unstable, changing urgency and pathway",
        "example": "Haemodynamically stable becomes septic or shocked",
    },
    {
        "id": "pregnancy",
        "family": Family.PATIENT,
        "label": "Pregnancy",
        "varies": "Pregnancy alters investigation and management choices",
        "example": "Same condition in a pregnant patient",
    },
    # --- §2A.2 Presentation ---------------------------------------------
    {
        "id": "timing",
        "family": Family.PRESENTATION,
        "label": "Timing",
        "varies": "Early, delayed or neglected presentation",
        "example": "Same disease seen on day 1 vs day 5 vs day 7",
    },
    {
        "id": "atypical",
        "family": Family.PRESENTATION,
        "label": "Atypical / masked",
        "varies": "Misleading or incomplete surface features",
        "example": "Elderly with vague symptoms and no fever; retrocaecal pattern",
    },
    {
        "id": "already-complicated",
        "family": Family.PRESENTATION,
        "label": "Already complicated",
        "varies": "The patient arrives with a complication present",
        "example": "Perforation, obstruction, abscess at first contact",
    },
    # --- §2A.3 Context (India-specific) ---------------------------------
    {
        "id": "resource-availability",
        "family": Family.CONTEXT,
        "label": "Resource availability",
        "varies": "What investigation or treatment can actually be done",
        "example": "No CT / MRI; no ICU bed; no blood products; specific implant unavailable",
    },
    {
        "id": "setting",
        "family": Family.CONTEXT,
        "label": "Setting",
        "varies": "The level and type of facility",
        "example": "District hospital vs tertiary centre",
    },
    {
        "id": "time-of-presentation",
        "family": Family.CONTEXT,
        "label": "Time of presentation",
        "varies": "Staffing and support available at that hour",
        "example": "Night duty, no senior immediately available",
    },
    # --- §2A.4 Course ----------------------------------------------------
    {
        "id": "post-op-complication",
        "family": Family.COURSE,
        "label": "Post-operative / post-procedure complication",
        "varies": "A complication develops after the intervention",
        "example": "Day-4 collection; wound dehiscence; post-op ileus not settling",
    },
    {
        "id": "first-line-failure",
        "family": Family.COURSE,
        "label": "Failure of first-line management",
        "varies": "The initial approach does not work",
        "example": "No response to conservative management — escalate?",
    },
    {
        "id": "deterioration",
        "family": Family.COURSE,
        "label": "Deterioration requiring escalation",
        "varies": "The patient worsens and needs a changed plan",
        "example": "Rising sepsis; falling output; need for higher care",
    },
    # --- §2A.5 Diagnostic uncertainty ------------------------------------
    {
        "id": "ambiguous-result",
        "family": Family.UNCERTAINTY,
        "label": "Ambiguous investigation result",
        "varies": "A test comes back equivocal",
        "example": "Borderline or non-diagnostic imaging / cytology",
    },
    {
        "id": "conflicting-findings",
        "family": Family.UNCERTAINTY,
        "label": "Conflicting findings",
        "varies": "Clinical and investigation findings disagree",
        "example": "Radiology-pathology mismatch; exam vs scan conflict",
    },
    {
        "id": "mimicking-differential",
        "family": Family.UNCERTAINTY,
        "label": "Mimicking differential",
        "varies": "Another condition presents like the logged entity",
        "example": "A differential that closely imitates the index diagnosis",
    },
    # --- Concept variation (pre-clinical) --------------------------------
    {
        "id": "altered-stimulus",
        "family": Family.CONCEPT,
        "label": "Altered stimulus",
        "varies": "The driving disturbance changes",
        "example": "Metabolic vs respiratory",
    },
    {
        "id": "compensation-over-time",
        "family": Family.CONCEPT,
        "label": "Compensation over time",
        "varies": "The response evolves with time",
        "example": "Acute versus chronic compensation",
    },
    {
        "id": "boundary-case",
        "family": Family.CONCEPT,
        "label": "Boundary / limit case",
        "varies": "The concept is pushed to its limit",
        "example": "The edge of the compensatory range",
    },
    {
        "id": "applied-clinical-link",
        "family": Family.CONCEPT,
        "label": "Applied clinical link",
        "varies": "The concept is tied to a clinical situation",
        "example": "The same mechanism seen in a patient",
    },
)

BY_ID: dict[str, dict[str, str]] = {axis["id"]: axis for axis in AXES}
ALL_IDS: list[str] = [axis["id"] for axis in AXES]


# Subject classes decide which families exist at all (§4A.2 and the §2A rules box).
CLINICAL = (Subject.GENERAL_SURGERY, Subject.ORTHOPAEDICS)
PARA_CLINICAL = (Subject.PATHOLOGY, Subject.FORENSIC_MEDICINE)
PRE_CLINICAL = (Subject.PHYSIOLOGY,)


def subject_class(subject: str) -> str:
    if subject in PRE_CLINICAL:
        return "pre-clinical"
    if subject in PARA_CLINICAL:
        return "para-clinical"
    return "clinical"


# §2 — the role changes the *type* of reasoning worth testing, so it gates which
# families are offered. Role shapes type, never severity.
ROLE_FAMILIES: dict[DopsRole, tuple[Family, ...]] = {
    # "Comprehension of what was watched"
    DopsRole.OBSERVED: (Family.PATIENT, Family.PRESENTATION, Family.UNCERTAINTY),
    # "Decision-making with the safety net removed"
    DopsRole.SUPERVISED: (
        Family.PATIENT,
        Family.PRESENTATION,
        Family.CONTEXT,
        Family.UNCERTAINTY,
    ),
    # "The edges — complications, atypical, constraints"
    DopsRole.INDEPENDENT: (
        Family.PATIENT,
        Family.PRESENTATION,
        Family.CONTEXT,
        Family.COURSE,
        Family.UNCERTAINTY,
    ),
    # Pre-clinical: no role levels, and no patient in the case at all.
    DopsRole.TOPIC: (Family.CONCEPT,),
}


def candidate_axes(subject: str, role: str) -> list[dict[str, str]]:
    """The axes a professor may certify for this entry.

    Filtered by competency subject and DOPS/role together, per §5's
    "candidate axes are now filtered by competency + DOPS/role".
    """
    families = set(ROLE_FAMILIES.get(DopsRole(role), ()))

    if subject_class(subject) == "pre-clinical":
        # The rules box: patient-factor and context are replaced by concept variation.
        families.discard(Family.PATIENT)
        families.discard(Family.CONTEXT)
        families.add(Family.CONCEPT)
    else:
        families.discard(Family.CONCEPT)

    return [axis for axis in AXES if axis["family"] in families]
