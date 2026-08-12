import { useEffect, useState } from 'react'

/** Stop short of the end. A bar that sits at 100% while nothing happens is the
 *  classic progress-bar lie; the jump to done comes with the text. */
const CEILING = 0.95

const clock = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`

/** Covers the case box while the recording is being turned into text.
 *
 *  The bar is determinate because a real number exists: transcription runs at
 *  roughly the speed the clip was spoken, and the clip's length is known the
 *  moment recording stops. So it counts against that rather than spinning
 *  forever with nothing to say.
 */
export function TranscribeLoader({ seconds }: { seconds: number }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const started = Date.now()
    // Driven from the client's own clock rather than the server's five-second
    // heartbeat, so the bar moves smoothly instead of in jumps.
    const tick = setInterval(() => setElapsed((Date.now() - started) / 1000), 120)
    return () => clearInterval(tick)
  }, [])

  const expected = Math.max(seconds, 1)
  const fraction = Math.min(elapsed / expected, CEILING)

  return (
    <div className="textbox-loader" role="status" aria-live="polite">
      <span className="textbox-spinner" aria-hidden />
      <p className="textbox-loader-title">Turning your recording into text</p>
      <div className="textbox-loader-bar" aria-hidden>
        <span style={{ width: `${Math.round(fraction * 100)}%` }} />
      </div>
      <p className="textbox-loader-note">
        {clock(Math.min(elapsed, expected))} of about {clock(expected)}
      </p>
    </div>
  )
}
