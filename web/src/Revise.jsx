import { useEffect, useRef, useState } from 'react'
import { getReview, reviewCard } from './api'

const CLOZE = /\{\{c1::(.*?)(?:::(.*?))?\}\}/g
const hideCloze = (s) => (s || '').replace(CLOZE, '［ ___ ］')
const showCloze = (s) => (s || '').replace(CLOZE, (_m, a) => a)
const withBreaks = (s) =>
  (s || '').split(/<br\s*\/?>/i).flatMap((p, i) => (i ? [<br key={i} />, p] : [p]))

export default function Revise({ onOpen, onBack, onDone }) {
  const [queue, setQueue] = useState(null)
  const [idx, setIdx] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState(null)
  const audioRef = useRef(null)
  const stopAtRef = useRef(null)

  useEffect(() => {
    getReview()
      .then((r) => setQueue(r.due || []))
      .catch((e) => setError(String(e.message || e)))
  }, [])

  const card = queue && idx < queue.length ? queue[idx] : null

  // Reset per-card transient state.
  useEffect(() => {
    setRevealed(false)
    setPlaying(false)
    const a = audioRef.current
    if (a) a.pause()
  }, [idx])

  function playClause() {
    const a = audioRef.current
    if (!a || !card || card.clause_start_ms == null) return
    if (playing && !a.paused) {
      a.pause()
      return
    }
    a.currentTime = card.clause_start_ms / 1000
    stopAtRef.current = card.clause_end_ms != null ? card.clause_end_ms / 1000 : null
    a.play()
    setPlaying(true)
  }
  function onAudioTime() {
    const a = audioRef.current
    if (a && stopAtRef.current != null && a.currentTime >= stopAtRef.current) {
      a.pause()
      stopAtRef.current = null
    }
  }

  function grade(g) {
    if (!card) return
    reviewCard(card.id, g).catch(() => {})
    const a = audioRef.current
    if (a) a.pause()
    setIdx((i) => i + 1)
  }

  if (error) return <p className="error">{error}</p>
  if (queue === null) return <p className="muted">loading review…</p>

  if (!card) {
    return (
      <main className="revise">
        <div className="revise-done">
          <p>{queue.length ? '✓ review complete' : 'nothing due — go shadow something.'}</p>
          <button className="ctl" onClick={onBack}>← back</button>
        </div>
      </main>
    )
  }

  return (
    <main className="revise">
      <audio
        ref={audioRef}
        src={`/audio/${card.video_id}.opus`}
        preload="none"
        onTimeUpdate={onAudioTime}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
      <div className="revise-bar">
        <button className="ctl" onClick={onBack}>← back</button>
        <span className="spacer" />
        <span className="muted">{idx + 1} / {queue.length}</span>
      </div>

      <div className="revise-card">
        <div className="revise-kind">{card.kind}</div>
        <div className="revise-front" lang="fr">
          {withBreaks(revealed ? showCloze(card.front) : hideCloze(card.front))}
        </div>
        <button className="ctl" onClick={playClause}>
          {playing ? '⏸ pause' : '▶ play clause'}
        </button>

        {!revealed ? (
          <div className="revise-actions">
            <button className="ctl reviewbtn" onClick={() => setRevealed(true)}>
              reveal
            </button>
          </div>
        ) : (
          <>
            <div className="revise-back">{withBreaks(card.back)}</div>
            {card.explanation && (
              <div className="revise-exp">
                <div className="explain-head">
                  {card.explanation.lemma} ·{' '}
                  <span className="muted">{card.explanation.pos}</span>
                </div>
                <div className="explain-body">{card.explanation.body}</div>
              </div>
            )}
            <button
              className="link revise-open"
              onClick={() => onOpen(card.video_id, card.clause_start_ms)}
            >
              open in player ↗ <span className="muted">({card.video_title})</span>
            </button>
            <div className="revise-grades">
              <button className="grade again" onClick={() => grade('again')}>again</button>
              <button className="grade good" onClick={() => grade('good')}>good</button>
              <button className="grade easy" onClick={() => grade('easy')}>easy</button>
            </div>
          </>
        )}
      </div>
    </main>
  )
}
