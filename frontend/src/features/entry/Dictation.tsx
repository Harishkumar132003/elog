import { useCallback, useEffect, useRef, useState } from 'react'

import { AlertIcon, MicIcon, StopIcon } from '../../components/icons'
import { MAX_RECORDING_SECONDS, transcribeRecording } from '../../lib/dictation'

type Phase = 'idle' | 'recording' | 'working'

/** Opus at 32 kbps is what speech is designed for — roughly 400 KB for a full
 *  90 seconds, comfortably inside any upload limit. */
const BITRATE = 32_000

/** Mono, because "speech to text models expect a single coherent input source",
 *  and without gain control so a quiet ward doesn't get amplified into hiss. */
const CONSTRAINTS: MediaStreamConstraints = {
  audio: {
    channelCount: 1,
    echoCancellation: false,
    autoGainControl: false,
    noiseSuppression: true,
  },
}

/** Voice input is only possible in a secure context — a page served over plain
 *  HTTP has no `mediaDevices` at all, so the button is hidden rather than shown
 *  and then failing. */
export const canDictate = (): boolean =>
  typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined
  // Chrome and Firefox give WebM/Opus; Safari only offers mp4. All three are
  // formats Corti accepts.
  const preferred = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']
  return preferred.find((type) => MediaRecorder.isTypeSupported(type))
}

const clock = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`

export function Dictation({
  onText,
  disabled,
}: {
  /** Called once with the finished transcript. Appending is the caller's job. */
  onText: (text: string) => void
  disabled?: boolean
}) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [elapsed, setElapsed] = useState(0)
  const [progress, setProgress] = useState(0)
  const [preview, setPreview] = useState('')
  const [error, setError] = useState<string | null>(null)
  /** Undecided until the device list comes back — the button appears only once
   *  we know there is something to record with. */
  const [hasMic, setHasMic] = useState<boolean | null>(null)

  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const startedAt = useRef(0)
  const abort = useRef<AbortController | null>(null)

  /** Release the microphone. Leaving the track live keeps the browser's
   *  recording indicator on, which looks like the app is still listening. */
  const release = useCallback(() => {
    recorder.current?.stream.getTracks().forEach((track) => track.stop())
    recorder.current = null
  }, [])

  // Recording and an in-flight transcription both have to stop if this unmounts,
  // because an abandoned Corti session is still a billed one.
  useEffect(() => {
    return () => {
      if (recorder.current?.state === 'recording') recorder.current.stop()
      release()
      abort.current?.abort()
    }
  }, [release])

  // `mediaDevices` existing does not mean a microphone exists — a desktop with no
  // mic has the API and fails only when you press the button. Asking for the
  // device list needs no permission (labels are hidden until granted, but the
  // count is not), so an absent mic hides the control instead of promising one.
  useEffect(() => {
    let live = true
    if (!canDictate()) {
      setHasMic(false)
      return
    }
    navigator.mediaDevices
      .enumerateDevices()
      .then((devices) => live && setHasMic(devices.some((d) => d.kind === 'audioinput')))
      // If the browser will not say, assume yes and let the button report the
      // real error — better than hiding a feature that might work.
      .catch(() => live && setHasMic(true))
    return () => {
      live = false
    }
  }, [])

  // The countdown, and the hard stop at the cap.
  useEffect(() => {
    if (phase !== 'recording') return
    const tick = setInterval(() => {
      const seconds = (Date.now() - startedAt.current) / 1000
      setElapsed(seconds)
      if (seconds >= MAX_RECORDING_SECONDS) recorder.current?.stop()
    }, 200)
    return () => clearInterval(tick)
  }, [phase])

  const transcribe = useCallback(
    async (clip: Blob, durationMs: number) => {
      setPhase('working')
      setPreview('')
      setProgress(0)
      abort.current = new AbortController()
      try {
        const result = await transcribeRecording(
          clip,
          durationMs,
          { onPartial: setPreview, onProgress: setProgress },
          abort.current.signal,
        )
        if (result.reason === 'no_speech' || !result.text.trim()) {
          setError("We didn't catch anything — try again a little closer to the mic")
        } else {
          onText(result.text)
          if (result.truncated) setError('That was long, so the end was trimmed to fit')
        }
      } catch (cause) {
        if (abort.current?.signal.aborted) return
        setError(cause instanceof Error ? cause.message : 'Could not transcribe that recording')
      } finally {
        setPhase('idle')
        setPreview('')
        abort.current = null
      }
    },
    [onText],
  )

  const start = useCallback(async () => {
    setError(null)
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS)
    } catch (cause) {
      // The browser's own errors are opaque; say what to actually do about it.
      const name = cause instanceof DOMException ? cause.name : ''
      setError(
        name === 'NotAllowedError'
          ? 'Microphone blocked. Allow it in your browser’s address bar, then try again'
          : name === 'NotFoundError'
            ? 'No microphone found on this device'
            : 'Could not start the microphone',
      )
      return
    }

    const mimeType = pickMimeType()
    const node = new MediaRecorder(stream, {
      audioBitsPerSecond: BITRATE,
      ...(mimeType ? { mimeType } : {}),
    })
    chunks.current = []
    startedAt.current = Date.now()

    node.ondataavailable = (event) => event.data.size && chunks.current.push(event.data)
    node.onstop = () => {
      const duration = Date.now() - startedAt.current
      const clip = new Blob(chunks.current, { type: node.mimeType })
      release()
      setElapsed(0)
      if (clip.size > 0 && duration > 400) void transcribe(clip, duration)
      else {
        setPhase('idle')
        setError('That was too short to hear')
      }
    }

    recorder.current = node
    node.start()
    setElapsed(0)
    setPhase('recording')
  }, [release, transcribe])

  const stop = useCallback(() => recorder.current?.stop(), [])

  const remaining = Math.max(MAX_RECORDING_SECONDS - elapsed, 0)

  if (hasMic === false) return null

  return (
    <div className="dictate">
      {phase === 'idle' && (
        <button
          type="button"
          className="btn btn-quiet dictate-start"
          onClick={start}
          disabled={disabled}
        >
          <MicIcon width={15} height={15} />
          Dictate
        </button>
      )}

      {phase === 'recording' && (
        <button type="button" className="btn dictate-stop" onClick={stop}>
          <StopIcon width={13} height={13} />
          Stop
          <em>{clock(remaining)}</em>
        </button>
      )}

      {phase === 'working' && (
        <span className="dictate-working" role="status" aria-live="polite">
          <span className="dictate-bar" aria-hidden>
            <span style={{ width: `${Math.round(progress * 100)}%` }} />
          </span>
          Getting your words…
        </span>
      )}

      {error && (
        <p className="dictate-error" role="alert">
          <AlertIcon width={13} height={13} />
          {error}
        </p>
      )}

      {/* The live transcript, shown while it is still arriving. It is not written
          into the case box until the whole recording is done — half a sentence
          that keeps changing is impossible to edit around. */}
      {phase === 'working' && preview && <p className="dictate-preview">{preview}</p>}
    </div>
  )
}
