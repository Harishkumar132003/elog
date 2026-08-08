"""The competency spine — the seed for an empty catalogue.

One competency per subject, exactly as named in the build specification (§1 and
§4). Nothing is added: the specification defines these five and no others.

This is no longer the live catalogue. A professor loads a real curriculum from
Configuration and the rows live in MongoDB; `app/services/catalogue.py` reads them.
These five are what a fresh database starts with, and their slugs are load-bearing —
`seed_if_empty()` writes them verbatim so entries logged before the catalogue moved
into the database still resolve.
"""

from app.core.constants import Subject

# id -> the competency. Ids are internal slugs; the specification gives no codes,
# and the reference screen shows the title alone.
CATALOGUE: tuple[dict[str, str], ...] = (
    {
        "id": "gs-surgical-emergencies",
        "subject": Subject.GENERAL_SURGERY,
        "title": "Diagnosis & management of common surgical emergencies",
        "logs": "A patient case",
    },
    {
        "id": "or-common-fractures",
        "subject": Subject.ORTHOPAEDICS,
        "title": "Management of common fractures",
        "logs": "A patient case",
    },
    {
        "id": "pa-specimen-interpretation",
        "subject": Subject.PATHOLOGY,
        "title": "Interpretation of the specimen and diagnosis",
        "logs": "A specimen / report",
    },
    {
        "id": "fm-cause-of-death",
        "subject": Subject.FORENSIC_MEDICINE,
        "title": "Cause-of-death reasoning and medico-legal duty",
        "logs": "An autopsy / medico-legal case",
    },
    {
        "id": "py-acid-base",
        "subject": Subject.PHYSIOLOGY,
        "title": "Acid-base physiology — regulation & compensation",
        "logs": "A topic / applied exercise",
    },
)

