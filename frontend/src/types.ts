export type Subject =
  | 'General Surgery'
  | 'Orthopaedics'
  | 'Pathology'
  | 'Forensic Medicine'
  | 'Physiology'

export type SubjectClass = 'clinical' | 'para-clinical' | 'pre-clinical'
export type DopsRole = 'observed' | 'supervised' | 'independent' | 'topic'
export type UserRole = 'resident' | 'professor'
export type EntryStatus = 'logged' | 'certified' | 'released' | 'answered'

export interface AuthUser {
  id: string
  email: string
  name: string
  role: UserRole
  professor_id: string | null
  department: string | null
  year: number | null
}

export interface Competency {
  id: string
  subject: Subject
  title: string
  logs: string
}

export interface RoleOption {
  value: DopsRole
  label: string
  hint: string
}

/** A subject and everything that follows from choosing it.
 *  The competencies themselves are fetched per subject — a loaded curriculum runs
 *  to dozens, and this response is held for the whole session. */
export interface SubjectMeta {
  value: Subject
  subject_class: SubjectClass
  competency_count: number
  roles: RoleOption[]
}

export interface Diagnosis {
  core: string
  qualifiers: string[]
  display: string
}
export interface Procedure {
  name: string
  detail: string | null
  display: string
  steps: { name: string; attempted: boolean }[]
}
export interface Patient {
  age: number | null
  sex: string | null
  display: string
}
export interface Omission {
  id: string
  short: string
  label: string
}

export interface Parsed {
  diagnosis: Diagnosis | null
  procedure: Procedure | null
  patient: Patient | null
  laterality: string | null
  omissions: Omission[]
}

export interface Analysis {
  parsed: Parsed
  /** The AI's proposal. A subject has many competencies, so the resident confirms it. */
  competency: Competency | null
  confidence: number
  source: string
}

/* ── configuration ─────────────────────────────────────────────────────── */

export interface CompetencyList {
  subject: Subject
  items: Competency[]
  updated_at: string | null
  updated_by: string | null
}

export interface CompetencySaveResult {
  subject: Subject
  added: number
  updated: number
  removed: number
  items: Competency[]
}

export interface ImportStarted {
  job_id: string
  pages_read: number
  pages_total: number
  chunks: number
}

export interface ImportJob {
  id: string
  subject: Subject
  status: 'running' | 'done' | 'failed'
  filename: string | null
  done: number
  total: number
  pages_read: number
  pages_total: number
  /** True when the PDF was longer than the import ceiling and was read in part. */
  truncated: boolean
  found: string[]
  error: string | null
}

export interface Entry {
  id: string
  resident_id: string
  professor_id: string | null
  subject: Subject
  narrative: string
  role: DopsRole
  role_label: string | null
  competency_id: string | null
  competency_title: string | null
  confirmed: boolean
  status: EntryStatus
  source: string
  parse_edited?: boolean
  diagnosis: string | null
  procedure: string | null
  patient_age: number | null
  patient_sex: string | null
  /** Only the detail endpoint returns the full parse; lists carry the flat fields. */
  parsed?: Parsed
  created_at: string
}

export const EMPTY_PARSE: Parsed = {
  diagnosis: null,
  procedure: null,
  patient: null,
  laterality: null,
  omissions: [],
}

export interface EntryPage {
  items: Entry[]
  total: number
  limit: number
  offset: number
}

/* ── screens 2 & 3 ─────────────────────────────────────────────────────── */
export interface Axis {
  id: string
  family: string
  label: string
  varies: string
  example: string
}

export interface AxisFamily {
  id: string
  label: string
  description: string
  axes: Axis[]
}

export interface AxisSuggestion {
  axis_id: string
  label: string
  reason: string
  example: string
}

export interface CandidateAxes {
  entry_id: string
  subject: Subject
  subject_class: SubjectClass
  role: DopsRole
  role_label: string
  competency_title: string | null
  families: AxisFamily[]
  certified: boolean
  /** The AI's shortlist — always a subset of `families`, empty until requested. */
  suggestions: AxisSuggestion[]
  critical_axis: string | null
  critical_why: string
}

export interface AxisChoice {
  axis_id: string
  discriminates: boolean
  parameter: string
  critical: boolean
  marks: number
}

/* ── screen 4 ──────────────────────────────────────────────────────────── */
export interface Question {
  id: number
  axis_id: string
  axis_label: string
  prompt: string
  cognitive: string
  affective: string
  psychomotor: string
  marks: number
  critical: boolean
}

export interface Exercise {
  entry_id: string
  status: EntryStatus
  source: string
  questions: Question[]
  competency_title: string | null
  role_label: string | null
  attempted: boolean
  /** Drafted questions stay with the professor until released. */
  released: boolean
  edited: boolean
  /** True while the questions are still being written in the background. */
  generating: boolean
  failed: boolean
}

export interface Result {
  question_id: number
  axis_label: string
  prompt: string
  /** What the resident actually wrote. */
  answer: string
  cognitive: string
  affective: string
  psychomotor: string
  marks: number
  marks_awarded: number
  critical: boolean
  critical_failed: boolean
  verdict: string
  feedback: string
}

export interface AttemptSummary {
  marks_awarded: number
  marks_available: number
  percentage: number
  critical_failed: boolean
  highest_cognitive: string | null
  outcome: string
}

export interface Attempt {
  entry_id: string
  competency_title: string | null
  source: string
  results: Result[]
  summary: AttemptSummary
  /** True while the answers are still being marked in the background. */
  marking: boolean
  created_at: string
}

/** One case screen in one request; absent stages are null rather than a 404. */
export interface CaseSnapshot {
  entry: Entry
  axes: CandidateAxes | null
  exercise: Exercise | null
  attempt: Attempt | null
}

/* ── professor dashboard ───────────────────────────────────────────────── */
export interface ResidentRow {
  id: string
  name: string
  year: number | null
  department: string | null
  cases: number
  answered: number
  critical_failures: number
}

export interface Dashboard {
  resident_id: string | null
  residents: ResidentRow[]
  totals: {
    cases: number
    awaiting_certification: number
    in_review: number
    ready_to_answer: number
    reasoned: number
  }
  /** One row per subject: the ratio, plus only the competencies with evidence. */
  coverage: {
    subject: Subject
    total: number
    covered: number
    percentage: number
    competencies: { id: string; title: string; logged: number; retired: boolean }[]
  }[]
  outcomes: { key: string; label: string; count: number }[]
  critical_failed: number
  attempts: number
  axes: {
    axis_id: string
    label: string
    family: string
    questions: number
    awarded: number
    available: number
    percentage: number
  }[]
  cognitive: { level: string; correct: number; asked: number; target: boolean }[]
  documentation: { id: string; label: string; missing: number; of: number; percentage: number }[]
  recent: {
    id: string
    resident_id: string
    resident_name: string | null
    diagnosis: string | null
    competency_title: string | null
    subject: string
    status: EntryStatus
    outcome: string | null
    percentage: number | null
    critical_failed: boolean
    created_at: string
  }[]
}
