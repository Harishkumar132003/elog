import { api } from './api'
import type {
  CompetencyList,
  CompetencySaveResult,
  ImportJob,
  ImportStarted,
  Subject,
} from '../types'

/** One subject's catalogue, plus who last changed it. */
export const getCatalogue = (subject: Subject) =>
  api<CompetencyList>(`/config/competencies?subject=${encodeURIComponent(subject)}`)

export interface CompetencyEdit {
  /** Absent on a row that does not exist yet. */
  id?: string | null
  title: string
  source?: 'manual' | 'pdf'
}

/** Saves the subject whole: the server works out what was added, changed and removed. */
export const saveCatalogue = (subject: Subject, items: CompetencyEdit[]) =>
  api<CompetencySaveResult>('/config/competencies', {
    method: 'PUT',
    body: { subject, items },
  })

/** Starts reading a curriculum PDF. Extraction runs on the server; poll for the result. */
export function startImport(subject: Subject, file: File): Promise<ImportStarted> {
  const form = new FormData()
  form.append('subject', subject)
  form.append('file', file)
  return api<ImportStarted>('/config/competencies/import', { method: 'POST', body: form })
}

export const getImport = (jobId: string) =>
  api<ImportJob>(`/config/competencies/import/${jobId}`)
