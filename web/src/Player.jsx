import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { getVideo, runPipeline, getIpa, addMark, deleteMark } from './api'

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5]
const clamp = (lo, hi, x) => Math.max(lo, Math.min(hi, x))

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

const Transcript = memo(function Transcript({ view, markPron, markMeaning }) {
  const cls = (gi) =>
    'w' + (markPron.has(gi) ? ' mp' : '') + (markMeaning.has(gi) ? ' mm' : '')
  if (view.segments) {
    return view.segments.map((seg) => (
      <div className="segment" data-seg={seg.seg_idx} key={seg.seg_idx}>
        {seg.tokens.map((t) => (
          <span className={cls(t.gi)} data-tok={t.gi} key={t.gi}>
            {t.text}
          </span>
        ))}
      </div>
    ))
  }
  return (
    <div className="rawwrap">
      {view.raw.map((t) => (
        <span className={cls(t.gi)} data-tok={t.gi} key={t.gi}>
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
  const [stepOn, setStepOn] = useState(false)
  const [rate, setRate] = useState(1)
  const [mode, setMode] = useState('shadow') // shadow | study (study: Slice 4)
  const [ipa, setIpa] = useState(null)
  const [marks, setMarks] = useState([])
  const [popover, setPopover] = useState(null) // {gi, segIdx, top, left}

  const audioRef = useRef(null)
  const transcriptRef = useRef(null)
  const rafRef = useRef(0)
  const lastTokRef = useRef(-1)
  const curSegRef = useRef(-1)
  const loopRef = useRef(false)
  const stepRef = useRef(false)
  const stepPrevSegRef = useRef(-1)
  const viewRef = useRef(null)
  const marksRef = useRef([])

  const view = useMemo(() => {
    if (!data) return null
    const starts = []
    const tokSeg = []
    const tokByGi = []
    let gi = 0
    const push = (tok, si) => {
      starts[gi] = tok.start_ms
      tokSeg[gi] = si
      tokByGi[gi] = tok
      tok.gi = gi
      gi += 1
    }
    if (data.render && data.render.length) {
      const segments = data.render.map((seg, si) => ({
        ...seg,
        tokens: seg.tokens.map((t) => {
          const tok = { ...t }
          push(tok, si)
          return tok
        }),
      }))
      const segMeta = data.render.map((s) => ({ start_ms: s.start_ms, end_ms: s.end_ms }))
      return { segments, raw: null, starts, tokSeg, tokByGi, segMeta }
    }
    const raw = data.words.map((w) => {
      const tok = { text: w.text, start_ms: w.start_ms, src_start: w.idx, src_end: w.idx }
      push(tok, -1)
      return tok
    })
    return { segments: null, raw, starts, tokSeg: null, tokByGi, segMeta: null }
  }, [data])

  viewRef.current = view
  loopRef.current = loopOn
  stepRef.current = stepOn
  marksRef.current = marks
  const pipelined = !!view?.segments

  // gi sets covered by a mark of each kind (overlap of token span vs mark span).
  const { markPron, markMeaning } = useMemo(() => {
    const mp = new Set()
    const mm = new Set()
    if (view) {
      for (const m of marks) {
        const set = m.kind === 'pron' ? mp : mm
        for (const t of view.tokByGi) {
          if (t.src_start <= m.span_end && m.span_start <= t.src_end) set.add(t.gi)
        }
      }
    }
    return { markPron: mp, markMeaning: mm }
  }, [view, marks])

  useEffect(() => {
    let alive = true
    setData(null)
    setError(null)
    setIpa(null)
    setMarks([])
    setPopover(null)
    lastTokRef.current = -1
    curSegRef.current = -1
    getVideo(videoId)
      .then((d) => {
        if (!alive) return
        setData(d)
        setMarks(d.marks || [])
      })
      .catch((e) => alive && setError(String(e.message || e)))
    getIpa(videoId)
      .then((d) => alive && setIpa(d))
      .catch(() => {})
    return () => {
      alive = false
      cancelAnimationFrame(rafRef.current)
    }
  }, [videoId])

  useEffect(() => {
    const a = audioRef.current
    if (a) {
      a.preservesPitch = true
      a.playbackRate = rate
    }
  }, [rate, data])

  useEffect(() => {
    if (pipelined) gotoSeg(0, { seek: false })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelined])

  function setCurSeg(i) {
    if (i === curSegRef.current) return
    curSegRef.current = i
    const c = transcriptRef.current
    if (!c) return
    const prev = c.querySelector('.segment.cur')
    if (prev) prev.classList.remove('cur')
    const el = c.querySelector(`[data-seg="${i}"]`)
    if (el) {
      el.classList.add('cur')
      el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }

  function setActiveTok(idx) {
    const c = transcriptRef.current
    if (!c) return
    if (idx !== lastTokRef.current) {
      const prev = lastTokRef.current
      if (prev >= 0) {
        const p = c.querySelector(`[data-tok="${prev}"]`)
        if (p) p.classList.remove('active')
      }
      if (idx >= 0) {
        const el = c.querySelector(`[data-tok="${idx}"]`)
        if (el) {
          el.classList.add('active')
          if (!viewRef.current?.tokSeg) el.scrollIntoView({ block: 'nearest' })
        }
      }
      lastTokRef.current = idx
    }
    const v = viewRef.current
    if (idx >= 0 && v?.tokSeg) setCurSeg(v.tokSeg[idx])
  }

  function syncHighlight() {
    const a = audioRef.current
    const v = viewRef.current
    if (a && v) setActiveTok(findTok(v.starts, a.currentTime * 1000))
    stepPrevSegRef.current = curSegRef.current // a seek isn't a clause boundary
  }

  function tick() {
    const a = audioRef.current
    const v = viewRef.current
    if (a && v) {
      let t = a.currentTime * 1000
      if (loopRef.current && v.segMeta) {
        const seg = v.segMeta[curSegRef.current]
        if (seg && t >= seg.end_ms) {
          a.currentTime = seg.start_ms / 1000
          t = seg.start_ms
        }
      }
      setActiveTok(findTok(v.starts, t))
      // Step mode: pause when we cross into a new clause (heard the previous one).
      if (stepRef.current && !loopRef.current && v.segMeta) {
        if (curSegRef.current !== stepPrevSegRef.current) {
          stepPrevSegRef.current = curSegRef.current
          a.pause()
        }
      }
    }
    rafRef.current = requestAnimationFrame(tick)
  }
  function startLoop() {
    stepPrevSegRef.current = curSegRef.current
    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(tick)
  }
  function stopLoop() {
    cancelAnimationFrame(rafRef.current)
    syncHighlight()
  }

  function gotoSeg(i, { seek = true, play = false } = {}) {
    const v = viewRef.current
    if (!v?.segMeta) return
    i = clamp(0, v.segMeta.length - 1, i)
    setCurSeg(i)
    stepPrevSegRef.current = i
    const a = audioRef.current
    if (seek && a) {
      a.currentTime = v.segMeta[i].start_ms / 1000
      if (play) a.play()
    }
  }

  function toggleMark(tok, kind) {
    if (!tok) return
    const span = [tok.src_start, tok.src_end]
    const exists = marksRef.current.some(
      (m) => m.kind === kind && m.span_start === span[0] && m.span_end === span[1],
    )
    if (exists) {
      deleteMark(videoId, span, kind).catch(() => {})
      setMarks((ms) =>
        ms.filter(
          (m) => !(m.kind === kind && m.span_start === span[0] && m.span_end === span[1]),
        ),
      )
    } else {
      addMark(videoId, span, kind).catch(() => {})
      setMarks((ms) => [
        ...ms,
        { span_start: span[0], span_end: span[1], kind, status: 'unknown' },
      ])
    }
  }

  function onClickTranscript(e) {
    const a = audioRef.current
    const v = viewRef.current
    const span = e.target.closest('[data-tok]')
    if (!span || !a || !v) return
    const gi = Number(span.dataset.tok)
    const segEl = span.closest('[data-seg]')
    if (segEl) setCurSeg(Number(segEl.dataset.seg))
    a.currentTime = v.starts[gi] / 1000
    a.play()
    if (mode === 'shadow') {
      const r = span.getBoundingClientRect()
      setPopover({ gi, segIdx: v.tokSeg ? v.tokSeg[gi] : -1, top: r.bottom + 4, left: r.left })
    }
  }

  useEffect(() => {
    function onKey(e) {
      if (/^(input|textarea|select)$/i.test(e.target.tagName)) return
      const a = audioRef.current
      const v = viewRef.current
      if (!a) return
      if (e.code === 'Escape') {
        setPopover(null)
      } else if (e.code === 'Space') {
        e.preventDefault()
        a.paused ? a.play() : a.pause()
      } else if (e.code === 'KeyH') {
        setReveal((r) => !r)
      } else if (e.code === 'KeyS') {
        setStepOn((s) => !s)
      } else if (e.code === 'KeyP' && v && lastTokRef.current >= 0) {
        toggleMark(v.tokByGi[lastTokRef.current], 'pron')
      } else if (e.code === 'KeyM' && v && lastTokRef.current >= 0) {
        toggleMark(v.tokByGi[lastTokRef.current], 'meaning')
      } else if (/^Digit[1-5]$/.test(e.code)) {
        setRate(SPEEDS[Number(e.code.slice(5)) - 1])
      } else if (pipelined) {
        if (e.code === 'ArrowRight') {
          e.preventDefault()
          gotoSeg(curSegRef.current + 1, { play: !a.paused })
        } else if (e.code === 'ArrowLeft') {
          e.preventDefault()
          gotoSeg(curSegRef.current - 1, { play: !a.paused })
        } else if (e.code === 'KeyR') {
          gotoSeg(curSegRef.current, { seek: true, play: true })
        } else if (e.code === 'KeyL') {
          setLoopOn((l) => !l)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelined, mode])

  async function rectify() {
    setPipelining(true)
    setError(null)
    try {
      await runPipeline(videoId)
      const d = await getVideo(videoId)
      setData(d)
      setMarks(d.marks || [])
      getIpa(videoId).then(setIpa).catch(() => {})
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setPipelining(false)
    }
  }

  if (error) return <p className="error">{error}</p>
  if (!data) return <p className="muted">loading transcript…</p>

  const popTok = popover && view ? view.tokByGi[popover.gi] : null
  const popSpan = popTok ? [popTok.src_start, popTok.src_end] : null
  const has = (kind) =>
    popSpan &&
    marks.some(
      (m) => m.kind === kind && m.span_start === popSpan[0] && m.span_end === popSpan[1],
    )

  return (
    <main className="player">
      <div className="playerhead">
        <div className="headrow">
          <h2 className="ptitle">{data.video.title}</h2>
          <div className="modes">
            <button
              className={`mode${mode === 'shadow' ? ' on' : ''}`}
              onClick={() => setMode('shadow')}
            >
              shadow
            </button>
            <button
              className={`mode${mode === 'study' ? ' on' : ''}`}
              onClick={() => setMode('study')}
              title="Translations & explanations land in Slice 4"
            >
              study
            </button>
          </div>
        </div>
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
          {pipelined && (
            <>
              <button
                className={`ctl${stepOn ? ' on' : ''}`}
                onClick={() => setStepOn((s) => !s)}
                title="Pause at each clause; Space to continue"
              >
                step (S){stepOn ? ' ✓' : ''}
              </button>
              <button
                className={`ctl${loopOn ? ' on' : ''}`}
                onClick={() => setLoopOn((l) => !l)}
              >
                loop (L){loopOn ? ' ✓' : ''}
              </button>
            </>
          )}
          {!pipelined && (
            <button className="ctl rectify" onClick={rectify} disabled={pipelining}>
              {pipelining ? 'rectifying…' : 'rectify & segment (LLM)'}
            </button>
          )}
        </div>
        <p className="hint">
          {pipelined
            ? 'click word: hear + IPA · P 🔊 / M ❓ mark · ←/→ clause · R replay · S step · L loop · 1–5 speed'
            : 'click word to jump · P/M mark · space play · rectify to unlock clauses'}
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
        <Transcript view={view} markPron={markPron} markMeaning={markMeaning} />
      </div>

      {popover && popTok && (
        <div
          className="ipapop"
          style={{ top: popover.top, left: popover.left }}
          onClick={(e) => e.stopPropagation()}
        >
          <button className="ipapop-x" onClick={() => setPopover(null)}>
            ✕
          </button>
          <div className="ipapop-word">{popTok.text.trim()}</div>
          <div className="ipapop-ipa">
            {ipa?.tokens?.[popover.gi] ? `/${ipa.tokens[popover.gi]}/` : '— no IPA —'}
          </div>
          {popover.segIdx >= 0 && ipa?.segments?.[popover.segIdx] && (
            <div className="ipapop-clause">clause: /{ipa.segments[popover.segIdx]}/</div>
          )}
          <div className="ipapop-marks">
            <button
              className={has('pron') ? 'on' : ''}
              onClick={() => toggleMark(popTok, 'pron')}
            >
              🔊 pron
            </button>
            <button
              className={has('meaning') ? 'on' : ''}
              onClick={() => toggleMark(popTok, 'meaning')}
            >
              ❓ meaning
            </button>
          </div>
        </div>
      )}
    </main>
  )
}
