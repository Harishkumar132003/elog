from enum import StrEnum


class Subject(StrEnum):
    GENERAL_SURGERY = "General Surgery"
    ORTHOPAEDICS = "Orthopaedics"
    PATHOLOGY = "Pathology"
    FORENSIC_MEDICINE = "Forensic Medicine"
    PHYSIOLOGY = "Physiology"


class Role(StrEnum):
    """Who is using the system."""

    RESIDENT = "resident"
    PROFESSOR = "professor"


class DopsRole(StrEnum):
    """What the resident did with the case (§2).

    The control is labelled DOPS because that is the term faculty know; what it
    really records is the role, and that gates the axis menu.
    """

    OBSERVED = "observed"
    SUPERVISED = "supervised"
    INDEPENDENT = "independent"
    TOPIC = "topic"


# §4A.2 — the same three levels are named differently by subject class, and
# pre-clinical entries have no role level at all.
ROLE_LABELS: dict[str, dict[DopsRole, tuple[str, str]]] = {
    "clinical": {
        DopsRole.OBSERVED: ("Observed", "watched it done"),
        DopsRole.SUPERVISED: ("Performed under supervision", "did it, senior present"),
        DopsRole.INDEPENDENT: ("Performed independently", "did it, unsupervised"),
    },
    "para-clinical": {
        DopsRole.OBSERVED: ("Assisted", "helped with it"),
        DopsRole.SUPERVISED: ("Reviewed", "reported it with a senior"),
        DopsRole.INDEPENDENT: ("Performed", "reported it yourself"),
    },
    "pre-clinical": {
        DopsRole.TOPIC: ("Topic-based", "a topic, not a patient"),
    },
}


def role_labels(subject_class: str) -> dict[DopsRole, tuple[str, str]]:
    return ROLE_LABELS.get(subject_class, ROLE_LABELS["clinical"])


class EntryStatus(StrEnum):
    """Where an entry sits in the four-screen loop."""

    LOGGED = "logged"          # 1 · resident saved it
    CERTIFIED = "certified"    # 3 · axes certified, questions drafted for review
    RELEASED = "released"      # 3 · professor approved the questions; resident can answer
    ANSWERED = "answered"      # 4 · resident completed the reasoning exercise
