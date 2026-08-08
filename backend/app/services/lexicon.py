"""Domain vocabulary used by the narrative parser.

All entries are lowercase and hyphen-free; `normalise()` puts incoming text into
the same shape so every lookup is an O(1) set/dict hit.
"""

# Head nouns that anchor a diagnosis phrase.
DIAGNOSIS_HEADS: frozenset[str] = frozenset(
    """
    fracture fractures dislocation subluxation hernia appendicitis cholecystitis
    cholelithiasis pancreatitis peritonitis obstruction perforation abscess
    osteomyelitis arthritis osteoarthritis carcinoma adenocarcinoma sarcoma
    lymphoma tumour tumor cyst ulcer laceration contusion abrasion burn
    haematoma hematoma anaemia anemia leukaemia leukemia poisoning overdose
    asphyxia strangulation sepsis cellulitis gangrene stricture fistula
    varicocele hydrocele thyroiditis goitre goiter injury wound sprain strain
    """.split()
)

# Tokens that may sit immediately left of the head noun and still belong to the
# core diagnosis (site / region / laterality), as opposed to descriptors.
SITE_TOKENS: frozenset[str] = frozenset(
    """
    distal proximal mid midshaft shaft supracondylar intertrochanteric
    subtrochanteric transcervical intracapsular extracapsular radius ulna
    humerus femur tibia fibula clavicle scaphoid metacarpal metatarsal
    calcaneus patella spine cervical lumbar thoracic pelvis acetabular
    acetabulum ankle wrist elbow shoulder hip knee hand foot finger toe
    inguinal umbilical femoral incisional epigastric hiatal ventral
    gallbladder appendix stomach gastric colonic colon rectal breast thyroid
    hepatic renal pulmonary splenic scalp skull frontal parietal occipital
    temporal facial mandibular nasal orbital greenstick left right bilateral
    """.split()
)

# Descriptors: reported alongside the diagnosis but never inside its core phrase.
QUALIFIER_PHRASES: tuple[str, ...] = (
    "intra articular",
    "extra articular",
    "dorsally angulated",
    "volarly angulated",
    "posteriorly displaced",
    "anteriorly displaced",
    "minimally displaced",
    "grossly comminuted",
    "comminuted",
    "displaced",
    "undisplaced",
    "impacted",
    "segmental",
    "compound",
    "open",
    "closed",
    "pathological",
    "obstructed",
    "strangulated",
    "incarcerated",
    "perforated",
    "gangrenous",
    "recurrent",
    "chronic",
    "acute",
)

LATERALITY: frozenset[str] = frozenset(("left", "right", "bilateral"))

# Procedure alias -> canonical display label.
PROCEDURES: dict[str, str] = {
    "orif": "ORIF",
    "open reduction and internal fixation": "ORIF",
    "open reduction internal fixation": "ORIF",
    "open reduction": "Open reduction",
    "closed reduction": "Closed reduction",
    "internal fixation": "Internal fixation",
    "external fixation": "External fixation",
    "k wire fixation": "K-wire fixation",
    "k wiring": "K-wire fixation",
    "k wire": "K-wire fixation",
    "intramedullary nailing": "Intramedullary nailing",
    "interlocking nailing": "Interlocking nailing",
    "arthroplasty": "Arthroplasty",
    "hemiarthroplasty": "Hemiarthroplasty",
    "arthroscopy": "Arthroscopy",
    "fasciotomy": "Fasciotomy",
    "cast application": "Cast application",
    "casting": "Cast application",
    "plaster application": "Cast application",
    "splinting": "Splinting",
    "traction": "Traction",
    "appendicectomy": "Appendicectomy",
    "appendectomy": "Appendicectomy",
    "cholecystectomy": "Cholecystectomy",
    "laparotomy": "Laparotomy",
    "laparoscopy": "Laparoscopy",
    "hernioplasty": "Hernioplasty",
    "herniorrhaphy": "Herniorrhaphy",
    "mesh repair": "Mesh repair",
    "mastectomy": "Mastectomy",
    "incision and drainage": "Incision & drainage",
    "debridement": "Debridement",
    "suturing": "Suturing",
    "wound toilet": "Wound toilet",
    "biopsy": "Biopsy",
    "excision biopsy": "Excision biopsy",
    "fnac": "FNAC",
    "fine needle aspiration": "FNAC",
    "grossing": "Specimen grossing",
    "frozen section": "Frozen section",
    "autopsy": "Medico-legal autopsy",
    "post mortem": "Medico-legal autopsy",
    "gastric lavage": "Gastric lavage",
    "intubation": "Endotracheal intubation",
    "catheterisation": "Catheterisation",
    "catheterization": "Catheterisation",
    "lumbar puncture": "Lumbar puncture",
    "spirometry": "Spirometry",
    "nerve conduction study": "Nerve conduction study",
    "reduction": "Reduction",
}

# Generic procedure words. A narrative often closes with "good reduction achieved"
# after the real operation; without this, that trailing generic term outranks the
# specific procedure it describes.
GENERIC_PROCEDURES: frozenset[str] = frozenset(
    {
        "reduction",
        "biopsy",
        "debridement",
        "suturing",
        "casting",
        "cast application",
        "plaster application",
        "splinting",
        "traction",
        "catheterisation",
        "catheterization",
        "wound toilet",
    }
)

# Implant / hardware head nouns — used to describe *how* the procedure was done.
DEVICE_HEADS: frozenset[str] = frozenset(
    """
    plate plating nail nails screw screws wire wires mesh graft cast slab
    splint drain stent catheter implant prosthesis fixator suture
    """.split()
)

# Tokens that terminate a leftward device-phrase walk.
PHRASE_STOPS: frozenset[str] = frozenset(
    """
    with using via under and or by to of the a an then after before
    proceeded performed done applied inserted placed fixed achieved
    """.split()
)

# Markers that mean a procedure was tried but is not the definitive one.
ATTEMPT_MARKERS: tuple[str, ...] = (
    "attempted",
    "attempt",
    "unsatisfactory",
    "unsuccessful",
    "failed",
    "abandoned",
    "not achieved",
    "could not",
)

# Documentation completeness checks: (id, chip label, full label, satisfying phrases).
# The short label is what the UI shows as a chip; the full one feeds the reasoning probe.
OMISSION_CHECKS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("laterality", "Side", "Side not documented", ("left", "right", "bilateral")),
    ("consent", "Consent", "Consent not recorded", ("consent", "consented")),
    (
        "anaesthesia",
        "Anaesthesia",
        "Anaesthesia not recorded",
        ("anaesthesia", "anesthesia", "spinal", "general", "block", "local", "sedation"),
    ),
    (
        "indication",
        "Mechanism",
        "Mechanism or indication not stated",
        (
            "fall", "fell", "trauma", "road traffic", "rta", "assault",
            "injury", "pain", "swelling", "history", "presented", "referred",
        ),
    ),
    (
        "complication",
        "Complications",
        "Complications not commented on",
        ("complication", "uneventful", "no complication", "intact", "stable"),
    ),
    (
        "followup",
        "Plan",
        "Post-procedure plan not recorded",
        (
            "follow up", "followup", "review", "physiotherapy", "mobilisation",
            "mobilization", "discharge", "advised", "plan",
        ),
    ),
)

# Words removed when tidying a free-text clause into a diagnosis phrase.
CLAUSE_NOISE: frozenset[str] = frozenset(
    """
    a an the with and of on for in patient case presented presents history
    diagnosed diagnosis known complaint complaints seen noted found
    """.split()
)
