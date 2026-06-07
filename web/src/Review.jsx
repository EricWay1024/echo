import { useEffect, useRef, useState } from 'react'
import { getVideo, explainMark, setCardStatus, getTranslation } from './api'

const key = (m) => `${m.span_start}-${m.span_end}`

// Render a string with literal <br> (as the LLM/Anki uses) as real line breaks.
const withBreaks = (s) =>
  (s || '').split(/<br\s*\/?>/i).flatMap((part, i) => (i ? [<br key={i} />, part] : [part]))

export default function Review({ videoId, onBack }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [explanations, setExplanations] = useState([])
  const [cards, setCards] = useState([])
  const [pending, setPending] = useState(() => new Set())
  const [busy, setBusy] = useState(false)
  const audioRef = useRef(null)
  const stopAtRef = useRef(null)
  const [trans, setTrans] = useState({}) // seg_idx -> translation | '…'
  const reqRef = useRef(new Set())

  useEffect(() => {
    let alive = true
    setTrans({})
    reqRef.current = new Set()
    getVideo(videoId)
      .then((d) => {
        if (!alive) return
        setData(d)
        setExplanations(d.explanations || [])
        setCards(d.cards || [])
      })
      .catch((e) => alive && setError(String(e.message || e)))
    return () => {
      alive = false
    }
  }, [videoId])

  // Fetch (cached) 中文 translations for every marked clause once data is loaded.
  useEffect(() => {
    if (!data?.render) return
    const segs = new Set()
    for (const m of data.marks || []) {
      const seg = data.render.find(
        (s) => s.span_start <= m.span_start && m.span_start <= s.span_end,
      )
      if (seg) segs.add(seg.seg_idx)
    }
    segs.forEach((si) => {
      if (reqRef.current.has(si)) return
      reqRef.current.add(si)
      setTrans((p) => ({ ...p, [si]: '…' }))
      getTranslation(videoId, si, 'zh')
        .then((r) => setTrans((p) => ({ ...p, [si]: r.text })))
        .catch(() => setTrans((p) => ({ ...p, [si]: '(translation failed)' })))
    })
  }, [data, videoId])

  if (error) return <p className="error">{error}</p>
  if (!data) return <p className="muted">loading…</p>

  const spanText = (s, e) => data.words.slice(s, e + 1).map((w) => w.text).join('').trim()

  function playClause(seg) {
    const a = audioRef.current
    if (!a) return
    a.currentTime = seg.start_ms / 1000
    stopAtRef.current = seg.end_ms / 1000
    a.play()
  }

  function onAudioTime() {
    const a = audioRef.current
    if (a && stopAtRef.current != null && a.currentTime >= stopAtRef.current) {
      a.pause()
      stopAtRef.current = null
    }
  }

  // The clause the mark sits in, with the marked tokens highlighted.
  const clause = (m) => {
    const seg = (data.render || []).find(
      (s) => s.span_start <= m.span_start && m.span_start <= s.span_end,
    )
    if (!seg) return null
    return (
      <>
        <div className="review-clause" lang="fr">
          <button className="clauseplay" title="play this clause" onClick={() => playClause(seg)}>
            ▶
          </button>
          {seg.tokens.map((t, i) => (
            <span
              key={i}
              className={t.src_start <= m.span_end && m.span_start <= t.src_end ? 'hl' : ''}
            >
              {t.text}
            </span>
          ))}
        </div>
        {trans[seg.seg_idx] !== undefined && (
          <div className="review-trans">{trans[seg.seg_idx]}</div>
        )}
      </>
    )
  }
  const meaningMarks = (data.marks || []).filter((m) => m.kind === 'meaning')
  const pronMarks = (data.marks || []).filter((m) => m.kind === 'pron')
  const expFor = (m) =>
    explanations.find((x) => x.span_start === m.span_start && x.span_end === m.span_end)
  const cardsFor = (m) =>
    cards.filter((c) => c.span_start === m.span_start && c.span_end === m.span_end)
  const todo = meaningMarks.filter((m) => !expFor(m))
  const acceptedCount = cards.filter((c) => c.status === 'accepted').length

  async function explainOne(m) {
    const k = key(m)
    setPending((p) => new Set(p).add(k))
    try {
      const r = await explainMark(videoId, [m.span_start, m.span_end])
      setExplanations((xs) => [
        ...xs.filter((x) => !(x.span_start === m.span_start && x.span_end === m.span_end)),
        { span_start: m.span_start, span_end: m.span_end, ...r.explanation },
      ])
      setCards((cs) => [
        ...cs.filter((c) => !(c.span_start === m.span_start && c.span_end === m.span_end)),
        ...r.cards,
      ])
    } catch {
      /* leave it pending-less; user can retry */
    } finally {
      setPending((p) => {
        const n = new Set(p)
        n.delete(k)
        return n
      })
    }
  }

  async function generateAll() {
    setBusy(true)
    const queue = meaningMarks.filter((m) => !expFor(m))
    let i = 0
    const worker = async () => {
      while (i < queue.length) await explainOne(queue[i++])
    }
    await Promise.all(Array.from({ length: Math.min(3, queue.length) }, worker))
    setBusy(false)
  }

  function cardStatus(id, status) {
    setCardStatus(id, status).catch(() => {})
    setCards((cs) => cs.map((c) => (c.id === id ? { ...c, status } : c)))
  }

  const card = (c) => (
    <div key={c.id} className={`card st-${c.status}`}>
      <div className="card-kind">{c.kind}</div>
      <div className="card-front">{withBreaks(c.front)}</div>
      <div className="card-back">{withBreaks(c.back)}</div>
      <div className="card-actions">
        <button className={c.status === 'accepted' ? 'on' : ''}
          onClick={() => cardStatus(c.id, 'accepted')}>accept</button>
        <button className={c.status === 'rejected' ? 'on' : ''}
          onClick={() => cardStatus(c.id, 'rejected')}>reject</button>
      </div>
    </div>
  )

  return (
    <main className="review">
      <audio
        ref={audioRef}
        src={`/audio/${videoId}.opus`}
        preload="none"
        onTimeUpdate={onAudioTime}
      />
      <div className="review-bar">
        <button className="ctl" onClick={onBack}>← shadow</button>
        <button className="ctl rectify" onClick={generateAll} disabled={busy || todo.length === 0}>
          {busy ? 'generating…' : `generate explanations & cards (${todo.length})`}
        </button>
        <span className="spacer" />
        <a className="ctl" href={`/api/videos/${videoId}/export?format=apkg`}>
          export .apkg ({acceptedCount})
        </a>
        <a className="ctl" href={`/api/videos/${videoId}/export?format=tsv`}>export .tsv</a>
      </div>

      <h2 className="ptitle">{data.video.title}</h2>

      <section>
        <h3 className="review-h">❓ meaning marks ({meaningMarks.length})</h3>
        {meaningMarks.length === 0 && (
          <p className="muted">none yet — mark ❓ spans while shadowing.</p>
        )}
        {meaningMarks.map((m) => {
          const exp = expFor(m)
          const isPending = pending.has(key(m))
          return (
            <div className="review-item" key={key(m)}>
              <div className="review-span">
                «{spanText(m.span_start, m.span_end)}»
                {m.note && <span className="review-note"> — {m.note}</span>}
              </div>
              {clause(m)}
              {exp ? (
                <>
                  <div className="explain-head">
                    {exp.lemma} · <span className="muted">{exp.pos}</span>
                  </div>
                  <div className="explain-body">{exp.body}</div>
                  {cardsFor(m).map(card)}
                </>
              ) : isPending ? (
                <p className="muted">explaining…</p>
              ) : (
                <button className="ctl" onClick={() => explainOne(m)}>explain</button>
              )}
            </div>
          )
        })}
      </section>

      {pronMarks.length > 0 && (
        <section>
          <h3 className="review-h">🔊 pronunciation marks ({pronMarks.length})</h3>
          <p className="muted">each becomes an audio card on export.</p>
          {pronMarks.map((m) => (
            <div className="review-item" key={key(m)}>
              <div className="review-span">
                «{spanText(m.span_start, m.span_end)}»
                {m.note && <span className="review-note"> — {m.note}</span>}
              </div>
              {clause(m)}
            </div>
          ))}
        </section>
      )}
    </main>
  )
}
