import { useEffect, useState } from 'react'
import { getVideo, explainMark, setCardStatus, setLexeme } from './api'

const key = (m) => `${m.span_start}-${m.span_end}`

export default function Review({ videoId, onBack }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [explanations, setExplanations] = useState([])
  const [cards, setCards] = useState([])
  const [pending, setPending] = useState(() => new Set())
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let alive = true
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

  if (error) return <p className="error">{error}</p>
  if (!data) return <p className="muted">loading…</p>

  const spanText = (s, e) => data.words.slice(s, e + 1).map((w) => w.text).join('').trim()
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

  function known(lemma) {
    if (lemma) setLexeme(lemma, 'fr', 'known').catch(() => {})
  }

  const card = (c) => (
    <div key={c.id} className={`card st-${c.status}`}>
      <div className="card-kind">{c.kind}</div>
      <div className="card-front">{c.front}</div>
      <div className="card-back">{c.back}</div>
      {c.rationale && <div className="card-rat">{c.rationale}</div>}
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
              {exp ? (
                <>
                  <div className="explain-head">
                    {exp.lemma} · <span className="muted">{exp.pos}</span>
                    <button className="knownbtn" onClick={() => known(exp.lemma)}>✓ known</button>
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
            </div>
          ))}
        </section>
      )}
    </main>
  )
}
