import { AlertIcon, CheckIcon } from '../../components/icons'
import type { Attempt } from '../../types'

const VERDICT_PILL: Record<string, string> = {
  correct: 'pill-ok',
  'partially correct': 'pill-warm',
  incorrect: 'pill-alert',
}

/** The recorded result — the roll-up to competency and Annexure I (§3.5).
 *
 *  `breakdown` is off where the questions are already on the page with their
 *  own marks beside them: the exercise page shows each result inside the card
 *  it belongs to, so listing them again here printed every question twice.
 */
export function ResultPanel({
  attempt,
  breakdown = true,
}: {
  attempt: Attempt
  breakdown?: boolean
}) {
  const { summary } = attempt
  const failed = summary.critical_failed

  return (
    <section className="card result">
      <header className={`result-head${failed ? ' is-failed' : ''}`}>
        <div className="result-score">
          <strong>{summary.percentage}%</strong>
          <small>
            {summary.marks_awarded} / {summary.marks_available} marks
          </small>
        </div>
        <div className="result-verdict">
          <span className="eyebrow">Recorded result</span>
          <h2>{summary.outcome}</h2>
          <p>
            {failed ? (
              <>
                A Critical item was answered wrongly. That is a disqualifying reasoning
                failure <em>regardless of the score</em>.
              </>
            ) : (
              <>
                Highest cognitive level reached:{' '}
                <strong>{summary.highest_cognitive ?? '—'}</strong>
              </>
            )}
          </p>
        </div>
        <span className={`result-flag ${failed ? 'is-failed' : 'is-passed'}`}>
          {failed ? <AlertIcon width={17} height={17} /> : <CheckIcon width={17} height={17} />}
          {failed ? 'Critical failed' : 'Critical passed'}
        </span>
      </header>

      <div className="result-rollup">
        <span className="eyebrow">Rolls up to</span>
        <p>{attempt.competency_title}</p>
      </div>

      {breakdown && (
      <ol className="results">
        {attempt.results.map((result) => (
          <li className={`result-item${result.critical_failed ? ' is-failed' : ''}`} key={result.question_id}>
            <div className="result-item-head">
              <span className="question-num">{result.question_id}</span>
              <div className="question-tags">
                <span className="pill pill-warm">{result.axis_label}</span>
                <span className={`pill ${VERDICT_PILL[result.verdict] ?? ''}`}>
                  {result.verdict}
                </span>
                {result.critical && (
                  <span className="pill pill-alert">
                    <AlertIcon width={11} height={11} />
                    Critical
                  </span>
                )}
              </div>
              <span className="result-marks">
                {result.marks_awarded}
                <em>/{result.marks}</em>
              </span>
            </div>

            <p className="question-prompt prose">{result.prompt}</p>

            {result.answer && (
              <blockquote className="result-answer">
                <span className="eyebrow">Their answer</span>
                <p>{result.answer}</p>
              </blockquote>
            )}

            {result.feedback && <p className="result-feedback">{result.feedback}</p>}

            <div className="result-domains">
              <span>
                COG <strong>{result.cognitive}</strong>
              </span>
              <span>
                AFF <strong>{result.affective}</strong>
              </span>
              <span>
                PSY <strong>{result.psychomotor}</strong>
              </span>
            </div>
          </li>
        ))}
      </ol>
      )}

      {/* {attempt.source !== 'corti' && (
        <p className="result-note">
          Marked without the AI service — these marks are provisional.
        </p>
      )} */}
    </section>
  )
}
