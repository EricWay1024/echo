import { memo, useEffect, useMemo, useRef, useState } from 'react'
import {
  getVideo, runPipeline, getIpa, addMark, deleteMark, getTranslation, saveProgress,
} from './api'

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

const Transcript = memo(function Transcript({ view, markPron, markMeaning, trans }) {
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
        <button className="trbtn" data-tr={seg.seg_idx} title="translate this clause">
          🌐
        </button>
        {trans[seg.seg_idx] !== undefined && (
          <div className="trans">{trans[seg.seg_idx]}</div>
        )}
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

export default function Player({ videoId, onReview }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [pipelining, setPipelining] = useState(false)
  const [reveal, setReveal] = useState(true)
  const [loopOn, setLoopOn] = useState(false)
  const [stepOn, setStepOn] = useState(false)
  const [rate, setRate] = useState(1)
  const [ipa, setIpa] = useState(null)
  const [marks, setMarks] = useState([])
  const [popover, setPopover] = useState(null)
  const [trans, setTrans] = useState({}) // segIdx -> text | '…'
  const [lang, setLang] = useState('zh')

  const audioRef = useRef(null)
  const transcriptRef = useRef(null)
  const popRef = useRef(null)
  const rafRef = useRef(0)
  const lastTokRef = useRef(-1)
  const curSegRef = useRef(-1)
  const loopRef = useRef(false)
  const stepRef = useRef(false)
  const stepPrevSegRef = useRef(-1)
  const viewRef = useRef(null)
  const marksRef = useRef([])
  const restoreRef = useRef(0) // resume position (ms) to seek once audio is ready
  const lastSaveRef = useRef(0)

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
    setTrans({})
    lastTokRef.current = -1
    curSegRef.current = -1
    restoreRef.current = 0
    getVideo(videoId)
      .then((d) => {
        if (!alive) return
        restoreRef.current = d.video.last_pos_ms || 0
        setData(d)
        setMarks(d.marks || [])
      })
      .catch((e) => alive && setError(String(e.message || e)))
    getIpa(videoId).then((d) => alive && setIpa(d)).catch(() => {})
    return () => {
      alive = false
      cancelAnimationFrame(rafRef.current)
      const a = audioRef.current
      if (a && a.currentTime > 0) {
        saveProgress(videoId, Math.round(a.currentTime * 1000)).catch(() => {})
      }
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
    // Highlight the first clause, unless we're about to restore a resume point.
    if (pipelined && restoreRef.current === 0) gotoSeg(0, { seek: false })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelined])

  // Seek to the saved resume point once the audio can seek.
  function onLoadedMeta() {
    const a = audioRef.current
    if (a && restoreRef.current > 0) {
      a.currentTime = restoreRef.current / 1000
      restoreRef.current = 0
      syncHighlight()
    }
  }

  // Best-effort save on tab close / navigation away.
  useEffect(() => {
    function onHide() {
      const a = audioRef.current
      if (a && a.currentTime > 0 && navigator.sendBeacon) {
        navigator.sendBeacon(
          `/api/videos/${videoId}/progress`,
          new Blob([JSON.stringify({ pos_ms: Math.round(a.currentTime * 1000) })],
            { type: 'application/json' }),
        )
      }
    }
    window.addEventListener('pagehide', onHide)
    return () => window.removeEventListener('pagehide', onHide)
  }, [videoId])

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
    stepPrevSegRef.current = curSegRef.current
  }

  function persist() {
    const a = audioRef.current
    if (a && a.currentTime > 0) {
      lastSaveRef.current = Date.now()
      saveProgress(videoId, Math.round(a.currentTime * 1000)).catch(() => {})
    }
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
      if (stepRef.current && !loopRef.current && v.segMeta) {
        if (curSegRef.current !== stepPrevSegRef.current) {
          stepPrevSegRef.current = curSegRef.current
          a.pause()
        }
      }
      if (Date.now() - lastSaveRef.current > 5000) persist() // resume point
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
    persist() // save resume point on pause/ended
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

  function toggleTranslate(seg) {
    if (trans[seg] !== undefined) {
      setTrans((p) => {
        const n = { ...p }
        delete n[seg]
        return n
      })
      return
    }
    setTrans((p) => ({ ...p, [seg]: '…' }))
    getTranslation(videoId, seg, lang)
      .then((r) => setTrans((p) => ({ ...p, [seg]: r.text })))
      .catch(() => setTrans((p) => ({ ...p, [seg]: '(translation failed)' })))
  }

  function switchLang(next) {
    setLang(next)
    setTrans({})
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
    if (!window.getSelection()?.isCollapsed) return
    const trBtn = e.target.closest('[data-tr]')
    if (trBtn) {
      toggleTranslate(Number(trBtn.dataset.tr))
      return
    }
    const a = audioRef.current
    const v = viewRef.current
    const span = e.target.closest('[data-tok]')
    if (!span || !a || !v) return
    const gi = Number(span.dataset.tok)
    const segEl = span.closest('[data-seg]')
    if (segEl) setCurSeg(Number(segEl.dataset.seg))
    a.currentTime = v.starts[gi] / 1000
    a.play()
    const r = span.getBoundingClientRect()
    const cont = transcriptRef.current.getBoundingClientRect()
    const POPW = 210
    const POPH = 210
    const GAP = 12
    let left = cont.right + GAP
    let top = r.top
    if (left + POPW > window.innerWidth - 8) left = cont.left - POPW - GAP
    if (left < 8) {
      left = Math.min(r.left, window.innerWidth - POPW - 8)
      top = r.bottom + 4
    }
    top = clamp(8, window.innerHeight - POPH - 8, top)
    setPopover({ type: 'ipa', gi, kind: 'meaning', note: '', top, left })
  }

  function onMouseUpTranscript() {
    const sel = window.getSelection()
    const v = viewRef.current
    const c = transcriptRef.current
    if (!sel || sel.isCollapsed || !sel.rangeCount || !v || !c) return
    const range = sel.getRangeAt(0)
    if (!c.contains(range.commonAncestorContainer)) return
    const elOf = (n) => (n.nodeType === 3 ? n.parentElement : n)?.closest?.('[data-tok]')
    const startEl = elOf(range.startContainer)
    const endEl = elOf(range.endContainer)
    if (!startEl || !endEl) return
    let a = Number(startEl.dataset.tok)
    let b = Number(endEl.dataset.tok)
    if (a > b) [a, b] = [b, a]
    if (b > a && range.endContainer.nodeType === 3) {
      const txt = v.tokByGi[b].text
      const lead = txt.length - txt.trimStart().length
      if (range.endOffset <= lead) b -= 1
    }
    const span = [v.tokByGi[a].src_start, v.tokByGi[b].src_end]
    const r = range.getBoundingClientRect()
    const POPW = 250
    const left = clamp(8, window.innerWidth - POPW - 8, r.left)
    const top = clamp(8, window.innerHeight - 130, r.bottom + 6)
    setPopover({ type: 'select', span, giStart: a, giEnd: b, kind: 'meaning', note: '', top, left })
  }

  function commitMark(span, kind, note) {
    const n = (note || '').trim() || null
    addMark(videoId, span, kind, n).catch(() => {})
    setMarks((ms) => [
      ...ms.filter(
        (m) => !(m.kind === kind && m.span_start === span[0] && m.span_end === span[1]),
      ),
      { span_start: span[0], span_end: span[1], kind, status: 'unknown', note: n },
    ])
  }

  function confirmMark() {
    if (popover?.type !== 'select') return
    commitMark(popover.span, popover.kind, popover.note)
    window.getSelection()?.removeAllRanges()
    setPopover(null)
  }

  function addMarkFromIpa() {
    if (popover?.type !== 'ipa' || !view) return
    const t = view.tokByGi[popover.gi]
    commitMark([t.src_start, t.src_end], popover.kind, popover.note)
    setPopover(null)
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
  }, [pipelined])

  useEffect(() => {
    if (!popover) return
    function onDown(e) {
      if (popRef.current && !popRef.current.contains(e.target)) setPopover(null)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [popover])

  useEffect(() => {
    if (popover?.type !== 'select') return
    const c = transcriptRef.current
    if (!c) return
    const els = []
    for (let g = popover.giStart; g <= popover.giEnd; g++) {
      const el = c.querySelector(`[data-tok="${g}"]`)
      if (el) {
        el.classList.add('selmark')
        els.push(el)
      }
    }
    return () => els.forEach((el) => el.classList.remove('selmark'))
  }, [popover])

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

  const popTok = popover?.type === 'ipa' && view ? view.tokByGi[popover.gi] : null
  const meaningCount = marks.filter((m) => m.kind === 'meaning').length

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
          onLoadedMetadata={onLoadedMeta}
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
          <div className="ctl langtoggle">
            <button className={lang === 'zh' ? 'on' : ''} onClick={() => switchLang('zh')}>
              中文
            </button>
            <button className={lang === 'en' ? 'on' : ''} onClick={() => switchLang('en')}>
              EN
            </button>
          </div>
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
          <button className="ctl reviewbtn" onClick={onReview}>
            review &amp; cards ({meaningCount}) →
          </button>
        </div>
        <p className="hint">
          click word: hear + IPA · 🌐 translate clause · select text → mark · ←/→
          clause · R replay · S step · L loop · 1–5 speed — explanations on the
          review page
        </p>
      </div>

      <div
        ref={transcriptRef}
        className={`transcript ${reveal ? '' : 'hidden'} ${
          pipelined ? 'segmented' : 'raw'
        }`}
        lang="fr"
        onClick={onClickTranscript}
        onMouseUp={onMouseUpTranscript}
      >
        <Transcript view={view} markPron={markPron} markMeaning={markMeaning} trans={trans} />
      </div>

      {popover?.type === 'ipa' && popTok && (
        <div
          ref={popRef}
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
          <div className="markpop-kind">
            <button
              className={popover.kind === 'pron' ? 'on' : ''}
              onClick={() => setPopover({ ...popover, kind: 'pron' })}
            >
              🔊 pron
            </button>
            <button
              className={popover.kind === 'meaning' ? 'on' : ''}
              onClick={() => setPopover({ ...popover, kind: 'meaning' })}
            >
              ❓ meaning
            </button>
          </div>
          <input
            className="markpop-note"
            placeholder="note (optional)…"
            value={popover.note}
            onChange={(e) => setPopover({ ...popover, note: e.target.value })}
            onKeyDown={(e) => {
              e.stopPropagation()
              if (e.key === 'Enter') addMarkFromIpa()
              else if (e.key === 'Escape') setPopover(null)
            }}
          />
          <div className="markpop-actions">
            <button className="primary" onClick={addMarkFromIpa}>
              add mark
            </button>
          </div>
        </div>
      )}

      {popover?.type === 'select' && (
        <div
          ref={popRef}
          className="markpop"
          style={{ top: popover.top, left: popover.left }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="markpop-kind">
            <button
              className={popover.kind === 'pron' ? 'on' : ''}
              onClick={() => setPopover({ ...popover, kind: 'pron' })}
            >
              🔊 pron
            </button>
            <button
              className={popover.kind === 'meaning' ? 'on' : ''}
              onClick={() => setPopover({ ...popover, kind: 'meaning' })}
            >
              ❓ meaning
            </button>
          </div>
          <input
            className="markpop-note"
            placeholder="note (optional)…"
            autoFocus
            value={popover.note}
            onChange={(e) => setPopover({ ...popover, note: e.target.value })}
            onKeyDown={(e) => {
              e.stopPropagation()
              if (e.key === 'Enter') confirmMark()
              else if (e.key === 'Escape') setPopover(null)
            }}
          />
          <div className="markpop-actions">
            <button onClick={() => setPopover(null)}>cancel</button>
            <button className="primary" onClick={confirmMark}>
              add mark
            </button>
          </div>
        </div>
      )}
    </main>
  )
}
