import { useCallback, useEffect, useState } from 'react'

import { ArrowIcon } from '../../components/icons'
import { getCase } from '../../lib/entries'
import { EMPTY_PARSE, type Attempt, type AuthUser, type CandidateAxes, type Entry, type Exercise } from '../../types'
import { CertifyPanel } from './CertifyPanel'
import { ExerciseEditor } from './ExerciseEditor'
import { ExercisePanel } from './ExercisePanel'
import { ResultPanel } from './ResultPanel'
import './flow.css'

const STAGES = [
  { id: 'logged', label: 'Logged' },
  { id: 'certified', label: 'Certified' },
  { id: 'released', label: 'Released' },
  { id: 'answered', label: 'Reasoned' },
] as const

interface Props {
  entryId: string
  user: AuthUser
  onBack: () => void
  onChanged: (entry: Entry) => void
}

/** One case, all the way through: analysis → certification → reasoning → result. */
export function CaseFlow({ entryId, user, onBack, onChanged }: Props) {
  const [entry, setEntry] = useState<Entry | null>(null)
  const [axes, setAxes] = useState<CandidateAxes | null>(null)
  const [exercise, setExercise] = useState<Exercise | null>(null)
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [loading, setLoading] = useState(true)

  const isProfessor = user.role === 'professor'

  const load = useCallback(async () => {
    setLoading(true)
    const snapshot = await getCase(entryId)
    setEntry(snapshot.entry)
    setAxes(snapshot.axes)
    setExercise(snapshot.exercise)
    setAttempt(snapshot.attempt)
    // This is the freshest the entry gets — push it back so the list behind
    // this screen does not keep showing a stage the case has already left.
    onChanged(snapshot.entry)
    setLoading(false)
  }, [entryId, onChanged])

  useEffect(() => {
    void load()
  }, [load])

  // Generation and marking now run in the background, so the screen waits by
  // polling rather than by holding a request open. Stops as soon as it lands.
  const pending = Boolean(exercise?.generating) || Boolean(attempt?.marking)
  useEffect(() => {
    if (!pending) return
    let live = true
    const timer = window.setInterval(async () => {
      if (!live) return
      const fresh = await getCase(entryId).catch(() => null)
      if (!live || !fresh) return
      setExercise(fresh.exercise)
      setAttempt(fresh.attempt)
      setEntry(fresh.entry)
    }, 2500)
    return () => {
      live = false
      window.clearInterval(timer)
    }
  }, [pending, exercise?.generating, attempt?.marking, entryId])

  if (loading || !entry) {
    return <div className="flow-loading">Loading case…</div>
  }

  const stageIndex = STAGES.findIndex((stage) => stage.id === entry.status)
  const parsed = entry.parsed ?? EMPTY_PARSE

  return (
    <>
      <div className="page-head">
        <div>
          <button type="button" className="btn btn-ghost flow-back" onClick={onBack}>
            ← All cases
          </button>
          <h1 className="page-title">{parsed.diagnosis?.core ?? entry.subject}</h1>
        </div>
        <ol className="stages">
          {STAGES.map((stage, index) => (
            <li
              key={stage.id}
              className={`stage${index <= stageIndex ? ' is-done' : ''}${index === stageIndex ? ' is-now' : ''}`}
            >
              <span className="stage-dot" aria-hidden />
              {stage.label}
            </li>
          ))}
        </ol>
      </div>

      {/* Screen 2 · the analysis everything downstream runs on */}
      <section className="card analysis">
        <div className="analysis-grid">
          <div className="analysis-cell analysis-competency">
            <span className="eyebrow">Competency</span>
            <p className="prose">{entry.competency_title}</p>
          </div>
          <div className="analysis-cell">
            <span className="eyebrow">Subject</span>
            <p>{entry.subject}</p>
          </div>
          <div className="analysis-cell">
            <span className="eyebrow">Role</span>
            <p>{entry.role_label ?? entry.role}</p>
          </div>
          <div className="analysis-cell">
            <span className="eyebrow">Procedure</span>
            <p>{parsed.procedure?.display ?? '—'}</p>
          </div>
          <div className="analysis-cell">
            <span className="eyebrow">Patient</span>
            <p>{parsed.patient?.display ?? 'not a patient case'}</p>
          </div>
        </div>

        <blockquote className="analysis-narrative prose">{entry.narrative}</blockquote>

        {parsed.omissions.length > 0 && (
          <div className="analysis-gaps">
            <span className="eyebrow">Left undocumented</span>
            <ul>
              {parsed.omissions.map((omission) => (
                <li key={omission.id} className="gap">
                  {omission.short}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* Screen 3 · certification, professor only */}
      {entry.status === 'logged' &&
        (isProfessor && axes ? (
          <CertifyPanel
            entryId={entryId}
            axes={axes}
            onCertified={(generated) => {
              setExercise(generated)
              const updated = { ...entry, status: 'certified' as const }
              setEntry(updated)
              onChanged(updated)
            }}
          />
        ) : (
          <section className="card waiting">
            <h2>Waiting for certification</h2>
            <p>
              Your professor decides which variations of this case discriminate, and which
              single mistake would be fatal. Your reasoning exercise is built from that.
            </p>
          </section>
        ))}

      {/* Questions are being written in the background */}
      {exercise?.generating && (
        <section className="card waiting">
          <h2>Writing the questions…</h2>
          <p>
            One question per axis you certified. This usually takes under a minute — you
            can leave this page and come back.
          </p>
        </section>
      )}

      {exercise?.failed && !exercise.generating && exercise.questions.length === 0 && (
        <section className="card waiting">
          <h2>The questions could not be written</h2>
          <p>Certify the axes again to retry.</p>
        </section>
      )}

      {/* Screen 3b · the professor reviews the draft before anyone else sees it */}
      {exercise && !exercise.generating && !exercise.released && !attempt && isProfessor && (
        <ExerciseEditor
          entryId={entryId}
          exercise={exercise}
          onChange={(updated) => {
            setExercise(updated)
            if (updated.released) {
              const next = { ...entry, status: 'released' as const }
              setEntry(next)
              onChanged(next)
            }
          }}
        />
      )}

      {/* The resident cannot see a draft at all. */}
      {entry.status === 'certified' && !isProfessor && !exercise?.generating && (
        <section className="card waiting">
          <h2>Your professor is reviewing the questions</h2>
          <p>
            The variations have been certified and your reasoning exercise is drafted. It
            will appear here once your professor releases it.
          </p>
        </section>
      )}

      {/* Screen 4 · the exercise */}
      {exercise && exercise.released && !attempt && (
        <ExercisePanel
          entryId={entryId}
          exercise={exercise}
          readOnly={isProfessor}
          onMarked={(marked) => {
            setAttempt(marked)
            const updated = { ...entry, status: 'answered' as const }
            setEntry(updated)
            onChanged(updated)
          }}
        />
      )}

      {attempt?.marking && (
        <section className="card waiting">
          <h2>Marking your answers…</h2>
          <p>
            Your answers are saved. The result appears here as soon as marking finishes —
            you can leave this page and come back.
          </p>
        </section>
      )}

      {attempt && !attempt.marking && <ResultPanel attempt={attempt} />}

      {attempt && !isProfessor && (
        <div className="flow-done">
          <button type="button" className="btn btn-quiet" onClick={onBack}>
            Back to all cases
            <ArrowIcon width={15} height={15} />
          </button>
        </div>
      )}
    </>
  )
}
