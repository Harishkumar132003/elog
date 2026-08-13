import { api } from './api'
import type { Case, DopsRole, Entry, Exercise, Question, Subject } from '../types'

export interface CreateCasePayload {
  subject: Subject
  narrative: string
  /** Who else was in the room. The creator is added server-side. */
  participants: DopsRole[]
  confirmed: boolean
  competency_id?: string | null
  /** Corrections to what the parser read; omitted keys are left as parsed. */
  diagnosis?: string
  procedure?: string
  patient_age?: number | null
  patient_sex?: string | null
}

export const createCase = (payload: CreateCasePayload) =>
  api<Case>('/cases', { method: 'POST', body: payload })

export const listCases = () => api<{ items: Case[]; total: number }>('/cases')

export const getCaseRecord = (caseId: string) => api<Case>(`/cases/${caseId}`)

/** Your own account of a case you were in. One per person per case. */
export const addLog = (caseId: string, narrative: string) =>
  api<Entry>(`/cases/${caseId}/logs`, { method: 'POST', body: { narrative } })

/** Every log on the case. Shared between the participants — they were all there. */
export const listLogs = (caseId: string) => api<Entry[]>(`/cases/${caseId}/logs`)

/** The roles a case can be staffed with — everyone but the professor. */
export const listRoles = () =>
  api<{ key: string; name: string; role: string; dops_role: DopsRole }[]>(
    '/cases/roles/available',
  )

/* ── the question builder ──────────────────────────────────────────────── */

export interface AddQuestionPayload {
  axis_id: string
  parameter: string
  marks: number
  critical: boolean
  /** The wording the professor approved. Sent on save so nothing is regenerated
   *  and the version they read is the version stored. */
  prompt?: string
  cognitive?: string
  affective?: string
}

/** Write one question and hand it back WITHOUT storing it.
 *
 *  One AI call, measured at 2–5s. Blocking rather than streamed: the server caps
 *  it well inside Cloudflare's idle limit and falls back to a scripted question,
 *  so the screen can never hang on it.
 *
 *  Abandoning a preview leaves no trace — nothing is written until save. */
export const previewQuestion = (entryId: string, payload: AddQuestionPayload) =>
  api<Question>(`/entries/${entryId}/questions/preview`, { method: 'POST', body: payload })

/** Append a question to this log's set. With `prompt` set nothing is generated. */
export const addQuestion = (entryId: string, payload: AddQuestionPayload) =>
  api<Exercise>(`/entries/${entryId}/questions`, { method: 'POST', body: payload })

export const removeQuestion = (entryId: string, questionId: number) =>
  api<Exercise>(`/entries/${entryId}/questions/${questionId}`, { method: 'DELETE' })
