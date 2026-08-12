import { apiStream } from './api'

/** Longest recording the server will accept. Mirrors `dictation_max_seconds`. */
export const MAX_RECORDING_SECONDS = 90

export interface TranscriptResult {
  text: string
  truncated: boolean
  /** "no_speech" when the recording held nothing audible — not an error. */
  reason: string | null
}

/** Send one recording and get the finished transcript back.
 *
 *  The reply is a stream rather than a single response because transcription
 *  takes about as long as the clip itself, and a connection that silent gets cut
 *  by Cloudflare. The stream is what keeps it alive, not what the screen shows:
 *  the entry form deliberately ignores the partial text and waits for the whole
 *  thing, because a sentence that rewrites itself mid-read looks broken.
 *
 *  `onPartial` and `onProgress` are offered for callers that do want the live
 *  view — nothing uses them today.
 */
export async function transcribeRecording(
  clip: Blob,
  durationMs: number,
  handlers: {
    onPartial?: (text: string) => void
    onProgress?: (fraction: number) => void
  },
  signal?: AbortSignal,
): Promise<TranscriptResult> {
  const form = new FormData()
  // The extension only has to keep the server's content sniffing happy; the
  // authoritative format is the mime_type field, taken from MediaRecorder.
  form.append('audio', clip, 'recording.webm')
  form.append('duration_ms', String(Math.round(durationMs)))
  form.append('mime_type', clip.type || 'audio/webm')

  let result: TranscriptResult | null = null
  let failure: string | null = null

  await apiStream(
    '/dictation/transcribe',
    form,
    ({ name, data }) => {
      if (name === 'partial') handlers.onPartial?.((data as { text: string }).text)
      else if (name === 'status') handlers.onProgress?.((data as { progress: number }).progress)
      else if (name === 'result') result = data as TranscriptResult
      // Reported inside the stream because the 200 status has already been sent.
      else if (name === 'error') failure = (data as { detail: string }).detail
    },
    signal,
  )

  if (failure) throw new Error(failure)
  return result ?? { text: '', truncated: false, reason: 'no_speech' }
}
