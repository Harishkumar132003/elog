"""The three domains of learning (specification §3).

Bloom's cognitive levels, Krathwohl's affective levels and Simpson's psychomotor
levels — the standard taxonomy medical faculty already know. Every reasoning
question is tagged with a level in each domain, plus marks and a Critical flag.
"""

# §3.1 — cognitive, lowest to highest.
COGNITIVE: tuple[tuple[str, str], ...] = (
    ("Remember", "Recall facts and basic concepts"),
    ("Understand", "Explain ideas or concepts"),
    ("Apply", "Use information in a new situation"),
    ("Analyse", "Draw connections; distinguish parts"),
    ("Evaluate", "Justify a decision or judgement"),
    ("Create", "Produce new or original work"),
)

# "Most reasoning questions sit at Apply, Analyse and Evaluate — the levels that
# test judgement, and the levels MCQ-style preparation reaches least."
COGNITIVE_TARGET = ("Apply", "Analyse", "Evaluate")

# §3.2 — affective, lowest to highest.
AFFECTIVE: tuple[tuple[str, str], ...] = (
    ("Receiving", "Willingness to attend to / be aware"),
    ("Responding", "Active participation / reaction"),
    ("Valuing", "Attaching worth to a behaviour or value"),
    ("Organising", "Reconciling values into a system"),
    ("Characterising", "Values become consistent behaviour"),
)

# §3.3 — psychomotor, lowest to highest. Assessed on real patients in the
# logbook, not by the reasoning engine; carried here for completeness.
PSYCHOMOTOR: tuple[tuple[str, str], ...] = (
    ("Perception", "Using senses to guide motor activity"),
    ("Set", "Readiness to act — mental, physical, emotional"),
    ("Guided response", "Early learning by imitation and trial"),
    ("Mechanism", "Learned responses become habitual and confident"),
    ("Complex overt response", "Skilled performance, smooth and accurate"),
    ("Adaptation", "Modifying the skill to fit a new situation"),
    ("Origination", "Creating new movement patterns for a situation"),
)

COGNITIVE_LEVELS = [name for name, _ in COGNITIVE]
AFFECTIVE_LEVELS = [name for name, _ in AFFECTIVE]
PSYCHOMOTOR_LEVELS = [name for name, _ in PSYCHOMOTOR]

# "not the active one" for most reasoning questions — an explicit opt-out value.
PSYCHOMOTOR_NOT_ASSESSED = "Not assessed"

DEFAULT_MARKS = 10


def describe(domain: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"level": level, "meaning": meaning} for level, meaning in domain]
