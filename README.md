# OpBook360 — Formative Reasoning

A resident writes a case in free text. The system reads it, maps it to one NMC competency,
and hands it to their professor, who certifies which variations of that case actually
discriminate — and which single mistake would be fatal. From that, questions are written,
answered in free text, and marked across the three domains of learning.

Built to `OpBook360_POC_Build_Spec_v1_2`.

```
e-log/
├── frontend/   React 18 + TypeScript + Vite
└── backend/    FastAPI + MongoDB (Motor) + Corti
```

## Run it

```bash
# 1. API
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.seed          # demo accounts, idempotent
.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000/docs

# 2. UI  (proxies /api to :8000)
cd frontend
npm install
npm run dev                               # http://localhost:5173
```

| Role | Email | Password |
| --- | --- | --- |
| Professor | `prof.rao@opbook360.ai` | `opbook360` |
| Resident | `resident@opbook360.ai` | `opbook360` |

One professor supervises three residents. A resident sees only their own cases; a professor
sees every case belonging to their own residents and nobody else's.

## The loop

| Screen | Who | What happens |
| --- | --- | --- |
| **1 · Log** | resident | Free text + subject + DOPS role. Corti parses it and names the competency; the resident confirms. |
| **2 · Analysis** | both | The confirmed competency and the candidate axes, filtered by competency **+** DOPS/role. |
| **3 · Certify** | professor | Tick which axes discriminate vs are cosmetic, set each parameter, and mark the one Critical item. |
| **4 · Reason** | resident | One question per certified axis, answered in a textbox. Marked, tagged COG/AFF/PSY, rolled up. |

Walk `backend/app/api/routes/flow.py` to see all four in one file.

## The two closed sets

Both come from the specification and **nothing has been added to either**.

**Competencies** — one per subject, §1 and §4 (`app/data/competencies.py`). The spec gives no
codes and its reference screen shows none, so neither does this.

**Variation axes** — the complete closed set of §2A (`app/data/axes.py`): 16 clinical axes in
five families, plus the four concept-variation axes that replace the patient-factor and
context families for pre-clinical subjects. A professor prunes; nobody adds live.

The closure is enforced in three places, not one:

1. The candidate list is filtered by competency **and** role before it is ever shown.
2. `POST /certify` refuses any axis outside that filtered set (422).
3. Corti's `outputSchema` uses an `enum`, so the model physically cannot emit an axis or
   competency that is not in the catalogue.

**Role gates type, never severity** (§2). `observed` offers patient-factor, presentation and
diagnostic-uncertainty; `supervised` adds context; `independent` adds course. Same case, same
marking — a different *kind* of question.

## How Corti is used

OAuth2 client credentials (`OPBOOK_CORTI_*`); tokens live 300 s and are cached in-process and
refreshed ahead of expiry behind a lock. Three templates, each created once and cached in the
`corti_templates` collection:

| Template | Does |
| --- | --- |
| `elog_parse` | Diagnosis, procedure, patient, competency, omissions from the raw entry |
| `question_gen` | One question per certified axis, with its Bloom cognitive and affective level |
| `answer_score` | Marks out of 10, a verdict and formative feedback per free-text answer |

Two things about Corti's schema layer, both found by testing rather than from the docs:

- **`outputSchema` supports `string`, `string` + `enum`, arrays of enum strings and `boolean`.
  Objects and object arrays return HTTP 500, and `integer` is rejected outright.** So anything
  structured is expressed as flat numbered sections — hence `q1_prompt`, `q1_cognitive`, and so
  on, rather than one section returning a list of objects.
- **Responses are keyed by Corti's own `sectionId`**, not by any key you send, and order is not
  preserved. Sections and templates are therefore created once and the `sectionId → key` map
  persisted; without it the generated fields cannot be told apart. Each template carries a
  fingerprint of its prompts, so editing a prompt provisions a fresh template instead of
  silently generating against stale wording.

Generation sends `X-Corti-Retention-Policy: none`, so no case text is stored on Corti's side.

### When calls happen

Never on typing, and never on opening a screen. A fully processed case costs **four** calls:

| Call | Trigger |
| --- | --- |
| Parse | resident presses **Analyse** |
| Axis shortlist | background task the moment the case is **saved** |
| Question generation | professor presses **Certify** |
| Marking | resident presses **Submit** |

Saving does *not* re-parse: `analyse_entry` memoises its answer for 15 minutes keyed on
subject + narrative, so the parse the resident already paid for is reused. Only genuine AI
answers are cached — a fallback is never pinned in place.

The shortlist is precomputed in the background at save, so the professor opens the certify
screen and it is already there (~0.15s). The manual **Suggest** button remains for when the
background task failed or has not finished, and the result is cached on the entry either way.

**Nothing depends on Corti being up.** The rule-based parser in `app/services/parser.py` runs on
every request and Corti merges over it field by field; question generation falls back to the
axis's own "what it varies" line. Every response carries a `source` of `corti`, `rules` or
`rules-fallback`, so a degraded path is visible rather than silent.

## Marking

Each question carries a cognitive level (Bloom), an affective level (Krathwohl), a psychomotor
level (Simpson — always `Not assessed`, since §3.3 puts that in the logbook, not here), marks,
and a Critical flag.

**The Critical flag is scored pass/fail independently of the marks.** A resident who answers the
other questions well and gets the fatal-error item wrong is recorded as a *Critical failure*,
not as a pass — that is the whole point of the flag, and it is verified end to end.

## Routes

Real URLs, not view state — every screen is linkable, survives a refresh, and works with
the back button.

| Path | Who |
| --- | --- |
| `/login` | signed out (signed-in users are bounced to their home) |
| `/` | redirects to `/new` for a resident, `/queue` for a professor |
| `/new` | resident — log a case |
| `/cases` · `/cases/:entryId` | both, scoped by role |
| `/queue` · `/residents` | professor only |
| `/reference` · `/settings` | both |

Hitting a protected path while signed out redirects to `/login` and **returns you to that
path after signing in**. A resident hitting a professor route is redirected home rather than
shown an error.

> Deploying: this is a client-routed SPA, so the host must serve `index.html` for unknown
> paths. `npm run dev` and `vite preview` already do; a static host needs a rewrite rule
> (Netlify `/* /index.html 200`, nginx `try_files $uri /index.html`).

## API

| Method | Route | Who |
| --- | --- | --- |
| `POST` | `/api/auth/login` · `/register` · `GET /me` | anyone |
| `GET` | `/api/auth/residents` | professor |
| `GET` | `/api/subjects` · `/competencies` · `/axes` · `/domains` | signed in |
| `POST` | `/api/entries/parse` · `POST /api/entries` | resident |
| `GET` | `/api/entries` · `/api/entries/{id}` | scoped by role |
| `GET` | `/api/entries/{id}/axes` · `/certification` | scoped by role |
| `POST` | `/api/entries/{id}/certify` | professor |
| `GET` | `/api/entries/{id}/exercise` | scoped by role |
| `POST` | `/api/entries/{id}/attempt` | resident |
| `GET` | `/api/entries/{id}/attempt` · `/api/stats` | scoped by role |

Collections: `users`, `entries`, `certifications`, `exercises`, `attempts`, `corti_templates`.
Visibility is enforced as a **query filter**, so a document outside the caller's scope is never
read — and asking for someone else's case returns 404, not a 403 that would confirm it exists.

## Design

Cool neutral surfaces, a deep navy rail, one modern sans. Colours are referenced by **role,
never by hue** (`--accent`, `--warm`, `--ok`, `--alert`), so retheming means editing
`styles/tokens.css` and nothing else:

- **accent** (indigo) — the system's own reasoning: competency, questions, progress
- **warm** (amber) — what a human asserted: the role claimed, the axes certified, the gaps
- **ok** (green) — a pass, a correct answer, a cleared Critical item
- **alert** (rose) — the Critical item, and only ever the Critical item

Screen 1 is two deliberate steps — write, then check what was read — and **no AI call is made
until the resident presses Analyse**. Pressing it again on unchanged text reuses the previous
result rather than spending another call.

## Not built

The Annexure I export (§3.5 calls the roll-up "represented, not fully implemented in the POC"),
cohort analytics, and the `/api/stats` charts. Screens 1–4 are complete.

`.env` holds live credentials and is gitignored — see `.env.example` for the shape.
# elog
