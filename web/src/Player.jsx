import { useEffect, useRef, useState } from 'react'
import { getVideo } from './api'

// Rightmost index with starts[i] <= tMs; -1 if before the first word.
function findWord(starts, tMs) {
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

export default function Player({ videoId }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const audioRef = useRef(null)
  const transcriptRef = useRef(null)
  const startsRef = useRef([])
  const rafRef = useRef(0)
  const lastIdxRef = useRef(-1)

  // Load transcript for this video.
  useEffect(() => {
    let alive = true
    setData(null)
    setError(null)
    lastIdxRef.current = -1
    getVideo(videoId)
      .then((d) => {
        if (!alive) return
        startsRef.current = d.words.map((w) => w.start_ms)
        setData(d)
      })
      .catch((e) => alive && setError(String(e.message || e)))
    return () => {
      alive = false
      cancelAnimationFrame(rafRef.current)
    }
  }, [videoId])

  // Move the highlight to word `next` via direct DOM (no React re-render/frame).
  function setActive(next) {
    const c = transcriptRef.current
    if (!c) return
    const prev = lastIdxRef.current
    if (prev === next) return
    if (prev >= 0 && c.children[prev]) c.children[prev].classList.remove('active')
    if (next >= 0 && c.children[next]) {
      const el = c.children[next]
      el.classList.add('active')
      el.scrollIntoView({ block: 'nearest' })
    }
    lastIdxRef.current = next
  }

  function syncHighlight() {
    const audio = audioRef.current
    if (audio) setActive(findWord(startsRef.current, audio.currentTime * 1000))
  }

  function tick() {
    syncHighlight()
    rafRef.current = requestAnimationFrame(tick)
  }

  function startLoop() {
    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(tick)
  }

  function stopLoop() {
    cancelAnimationFrame(rafRef.current)
    syncHighlight() // settle on the current word once after stopping
  }

  function onWordClick(e) {
    const span = e.target.closest('[data-idx]')
    if (!span || !audioRef.current || !data) return
    const idx = Number(span.dataset.idx)
    audioRef.current.currentTime = data.words[idx].start_ms / 1000
    audioRef.current.play()
  }

  // Spacebar toggles play/pause (unless typing in a field).
  useEffect(() => {
    function onKey(e) {
      if (e.code !== 'Space') return
      if (/^(input|textarea)$/i.test(e.target.tagName)) return
      e.preventDefault()
      const a = audioRef.current
      if (a) (a.paused ? a.play() : a.pause())
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

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
        <p className="hint">click any word to jump · space to play/pause</p>
      </div>

      <div ref={transcriptRef} className="transcript" lang="fr" onClick={onWordClick}>
        {data.words.map((w) => (
          <span key={w.idx} data-idx={w.idx} className="w">
            {w.text}
          </span>
        ))}
      </div>
    </main>
  )
}
