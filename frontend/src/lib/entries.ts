import { api } from './api'
import type {
  Analysis,
  Attempt,
  AuthUser,
  AxisChoice,
  CandidateAxes,
  Competency,
  DopsRole,
  Entry,
  EntryPage,
  CaseSnapshot,
  Dashboard,
  Exercise,
  Question,
  Subject,
  SubjectMeta,
} from '../types'

/* ── reference data ────────────────────────────────────────────────────── */

let subjectCache: Promise<SubjectMeta[]> | null = null

/** Subjects, their class, how many competencies they hold and their role labels.
 *  Static for the process, so it is fetched once and shared. */
export function getSubjects(): Promise<SubjectMeta[]> {
  subjectCache ??= api<SubjectMeta[]>('/subjects').catch((error) => {
    subjectCache = null // let a later attempt retry
    throw error
  })
  return subjectCache
}

const competencyCache = new Map<Subject, Promise<Competency[]>>()

/** One subject's competencies, for the entry screen's dropdown.
 *  Memoised per subject; `forgetCompetencies` clears it after a catalogue edit. */
export function getCompetencies(subject: Subject): Promise<Competency[]> {
  let pending = competencyCache.get(subject)
  if (!pending) {
    pending = api<Competency[]>(`/competencies?subject=${encodeURIComponent(subject)}`).catch(
      (error) => {
        competencyCache.delete(subject)
        throw error
      },
    )
    competencyCache.set(subject, pending)
  }
  return pending
}

export const forgetCompetencies = (subject?: Subject): void => {
  if (subject) competencyCache.delete(subject)
  else competencyCache.clear()
}

/* ── screen 1 ──────────────────────────────────────────────────────────── */

export const parseEntry = (subject: Subject, narrative: string, signal?: AbortSignal) =>
  api<Analysis>('/entries/parse', { method: 'POST', body: { subject, narrative }, signal })

export interface CreateEntryPayload {
  subject: Subject
  narrative: string
  role: DopsRole
  confirmed: boolean
  /** The competency the resident settled on; omitted keeps the AI's pick. */
  competency_id?: string | null
  /** Corrections to what the parser read; omitted keys are left as parsed. */
  diagnosis?: string
  procedure?: string
  patient_age?: number | null
  patient_sex?: string | null
}

export const createEntry = (payload: CreateEntryPayload) =>
  api<Entry>('/entries', { method: 'POST', body: payload })

export const listEntries = (params: { limit?: number; status?: string } = {}) => {
  const query = new URLSearchParams()
  if (params.limit) query.set('limit', String(params.limit))
  if (params.status) query.set('status', params.status)
  const suffix = query.toString()
  return api<EntryPage>(`/entries${suffix ? `?${suffix}` : ''}`)
}

export const getEntry = (entryId: string) => api<Entry>(`/entries/${entryId}`)

/* ── screens 2 & 3 ─────────────────────────────────────────────────────── */

export const getCandidateAxes = (entryId: string) =>
  api<CandidateAxes>(`/entries/${entryId}/axes`)

/** Entry, axes, exercise and attempt in one request. */
export const getCase = (entryId: string) => api<CaseSnapshot>(`/entries/${entryId}/case`)

export interface AxisHint {
  suggestions: { axis_id: string; label: string; reason: string; example: string }[]
  critical_axis: string | null
  critical_why: string
  source: string
}

/** Shortlist the axes worth testing. Cached server-side per case. */
export const suggestAxes = (entryId: string) =>
  api<AxisHint>(`/entries/${entryId}/axes/suggest`, { method: 'POST' })

export const certify = (entryId: string, axes: AxisChoice[]) =>
  api<Exercise>(`/entries/${entryId}/certify`, { method: 'POST', body: { axes } })

/* ── screen 4 ──────────────────────────────────────────────────────────── */

/** Professor rewording the draft. Refused once the exercise is released. */
export const updateExercise = (entryId: string, questions: Question[]) =>
  api<Exercise>(`/entries/${entryId}/exercise`, {
    method: 'PUT',
    body: {
      questions: questions.map((q) => ({
        id: q.id,
        prompt: q.prompt,
        marks: q.marks,
        critical: q.critical,
        cognitive: q.cognitive,
        affective: q.affective,
      })),
    },
  })

/** Hands the exercise to the resident. Until this they cannot see it. */
export const releaseExercise = (entryId: string) =>
  api<Exercise>(`/entries/${entryId}/exercise/release`, { method: 'POST' })

export const submitAttempt = (entryId: string, answers: { question_id: number; answer: string }[]) =>
  api<Attempt>(`/entries/${entryId}/attempt`, { method: 'POST', body: { answers } })

/* ── people ────────────────────────────────────────────────────────────── */

export const listResidents = () => api<AuthUser[]>('/auth/residents')

/** Professor-only aggregate; omit residentId for the whole cohort. */
export const getDashboard = (residentId?: string | null) =>
  api<Dashboard>(`/professor/dashboard${residentId ? `?resident_id=${residentId}` : ''}`)
