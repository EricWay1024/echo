import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { getVideo, runPipeline } from './api'

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5]

// Rightmost index with starts[i] <= tMs; -1 if before the first.
function findTok(starts, tMs) {
  let lo = 0
  let hi = starts.length - 1
  let ans = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (starts[mid] <= tMs) {
      ans = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  return ans
}

// Pure render of the token stream — memoized so playback/control state changes
// don't re-render thousands of spans. Tokens carry a global index (data-tok)
// for the karaoke highlighter; segments carry data-seg for selection/looping.
const Transcript = memo(function Transcript({ view }) {
  if (view.segments) {
    return view.segments.map((seg) => (
      <div className="segment" data-seg={seg.seg_idx} key={seg.seg_idx}>
        {seg.tokens.map((t) => (
          <span className="w" data-tok={t.gi} key={t.gi}>
            {t.text}
          </span>
        ))}
      </div>
    ))
  }
  return (
    <div className="rawwrap">
      {view.raw.map((t) => (
        <span className="w" data-tok={t.gi} key={t.gi}>
          {t.text}
        </span>
      ))}
    </div>
  )
})

export default function Player({ videoId }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [pipelining, setPipelining] = useState(false)
  const [reveal, setReveal] = useState(true)
  const [loopOn, setLoopOn] = useState(false)
  const [rate, setRate] = useState(1)

  const audioRef = useRef(null)
  const transcriptRef = useRef(null)
  const rafRef = useRef(0)
  const lastTokRef = useRef(-1)
  const selSegRef = useRef(0)
  const loopRef = useRef(false)
  const viewRef = useRef(null)

  // Build the token stream (segmented when pipelined, else raw words).
  const view = useMemo(() => {
    if (!data) return null
    const starts = []
    let gi = 0
    if (data.render && data.render.length) {
      const segments = data.render.map((seg) => ({
        ...seg,
        tokens: seg.tokens.map((t) => {
          const tok = { ...t, gi }
          starts[gi] = t.start_ms
          gi += 1
          return tok
        }),
      }))
      const segMeta = data.render.map((s) => ({
        start_ms: s.start_ms,
        end_ms: s.end_ms,
      }))
      return { segments, raw: null, starts, segMeta }
    }
    const raw = data.words.map((w) => {
      const tok = { text: w.text, gi, start_ms: w.start_ms }
      starts[gi] = w.start_ms
      gi += 1
      return tok
    })
    return { segments: null, raw, starts, segMeta: null }
  }, [data])

  viewRef.current = view
  loopRef.current = loopOn
  const pipelined = !!view?.segments

  // Load transcript for this video.
  useEffect(() => {
    let alive = true
    setData(null)
    setError(null)
    lastTokRef.current = -1
    selSegRef.current = 0
    getVideo(videoId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e.message || e)))
    return () => {
      alive = false
      cancelAnimationFrame(rafRef.current)
    }
  }, [videoId])

  // Apply playback rate (pitch preserved).
  useEffect(() => {
    const a = audioRef.current
    if (a) {
      a.preservesPitch = true
      a.playbackRate = rate
    }
  }, [rate, data])

  // Highlight first segment once the segmented view is ready.
  useEffect(() => {
    if (pipelined) selectSeg(0, { seek: false })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelined])

  function setActiveTok(idx) {
    const c = transcriptRef.current
    if (!c || idx === lastTokRef.current) return
    const prev = lastTokRef.current
    if (prev >= 0) {
      const p = c.querySelector(`[data-tok="${prev}"]`)
      if (p) p.classList.remove('active')
    }
    if (idx >= 0) {
      const el = c.querySelector(`[data-tok="${idx}"]`)
      if (el) {
        el.classList.add('active')
        el.scrollIntoView({ block: 'nearest' })
      }
    }
    lastTokRef.current = idx
  }

  function syncHighlight() {
    const a = audioRef.current
    const v = viewRef.current
    if (a && v) setActiveTok(findTok(v.starts, a.currentTime * 1000))
  }

  function tick() {
    const a = audioRef.current
    const v = viewRef.current
    if (a && v) {
      const t = a.currentTime * 1000
      setActiveTok(findTok(v.starts, t))
      if (loopRef.current && v.segMeta) {
        const seg = v.segMeta[selSegRef.current]
        if (seg && t >= seg.end_ms) a.currentTime = seg.start_ms / 1000
      }
    }
    rafRef.current = requestAnimationFrame(tick)
  }
  function startLoop() {
    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(tick)
  }
  function stopLoop() {
    cancelAnimationFrame(rafRef.current)
    syncHighlight()
  }

  function selectSeg(i, { seek = true, play = false } = {}) {
    const v = viewRef.current
    if (!v?.segMeta) return
    i = Math.max(0, Math.min(v.segMeta.length - 1, i))
    selSegRef.current = i
    const c = transcriptRef.current
    if (c) {
      const prev = c.querySelector('.segment.sel')
      if (prev) prev.classList.remove('sel')
      const el = c.querySelector(`[data-seg="${i}"]`)
      if (el) {
        el.classList.add('sel')
        el.scrollIntoView({ block: 'nearest' })
      }
    }
    const a = audioRef.current
    if (seek && a) {
      a.currentTime = v.segMeta[i].start_ms / 1000
      if (play) a.play()
    }
  }

  function onClickTranscript(e) {
    const a = audioRef.current
    const v = viewRef.current
    const span = e.target.closest('[data-tok]')
    if (!span || !a || !v) return
    const gi = Number(span.dataset.tok)
    const segEl = span.closest('[data-seg]')
    if (segEl) selectSeg(Number(segEl.dataset.seg), { seek: false })
    a.currentTime = v.starts[gi] / 1000
    a.play()
  }

  // Keyboard shortcuts.
  useEffect(() => {
    function onKey(e) {
      if (/^(input|textarea|select)$/i.test(e.target.tagName)) return
      const a = audioRef.current
      if (!a) return
      if (e.code === 'Space') {
        e.preventDefault()
        a.paused ? a.play() : a.pause()
      } else if (e.code === 'KeyH') {
        setReveal((r) => !r)
      } else if (/^Digit[1-5]$/.test(e.code)) {
        setRate(SPEEDS[Number(e.code.slice(5)) - 1])
      } else if (pipelined) {
        if (e.code === 'ArrowRight') {
          e.preventDefault()
          selectSeg(selSegRef.current + 1, { play: !a.paused })
        } else if (e.code === 'ArrowLeft') {
          e.preventDefault()
          selectSeg(selSegRef.current - 1, { play: !a.paused })
        } else if (e.code === 'KeyR') {
          selectSeg(selSegRef.current, { seek: true, play: true })
        } else if (e.code === 'KeyL') {
          setLoopOn((l) => !l)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pipelined])

  async function rectify() {
    setPipelining(true)
    setError(null)
    try {
      await runPipeline(videoId)
      setData(await getVideo(videoId))
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setPipelining(false)
    }
  }

  if (error) return <p className="error">{error}</p>
  if (!data) return <p className="muted">loading transcript…</p>

  return (
    <main className="player">
      <div className="playerhead">
        <h2 className="ptitle">{data.video.title}</h2>
        <audio
          ref={audioRef}
          className="audio"
          controls
          preload="auto"
          src={`/audio/${videoId}.opus`}
          onPlay={startLoop}
          onPause={stopLoop}
          onEnded={stopLoop}
          onSeeked={syncHighlight}
        />
        <div className="controls">
          <label className="ctl">
            speed
            <select value={rate} onChange={(e) => setRate(Number(e.target.value))}>
              {SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s}×
                </option>
              ))}
            </select>
          </label>
          <button className="ctl" onClick={() => setReveal((r) => !r)}>
            {reveal ? 'hide text (H)' : 'reveal text (H)'}
          </button>
          {pipelined ? (
            <button
              className={`ctl${loopOn ? ' on' : ''}`}
              onClick={() => setLoopOn((l) => !l)}
            >
              loop segment (L){loopOn ? ' ✓' : ''}
            </button>
          ) : (
            <button className="ctl rectify" onClick={rectify} disabled={pipelining}>
              {pipelining ? 'rectifying…' : 'rectify & segment (LLM)'}
            </button>
          )}
        </div>
        <p className="hint">
          {pipelined
            ? 'click a word to jump · ←/→ segment · R replay · L loop · 1–5 speed · space play'
            : 'click a word to jump · space play/pause · rectify to unlock clause loops'}
        </p>
      </div>

      <div
        ref={transcriptRef}
        className={`transcript ${reveal ? '' : 'hidden'} ${
          pipelined ? 'segmented' : 'raw'
        }`}
        lang="fr"
        onClick={onClickTranscript}
      >
        <Transcript view={view} />
      </div>
    </main>
  )
}
