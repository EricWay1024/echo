import { useEffect, useState } from 'react'
import { listVideos, getReview } from './api'
import Library from './Library'
import Player from './Player'
import Review from './Review'
import Revise from './Revise'

export default function App() {
  const [videos, setVideos] = useState(null)
  const [selected, setSelected] = useState(null)
  const [reviewing, setReviewing] = useState(false)
  const [revising, setRevising] = useState(false)
  const [startMs, setStartMs] = useState(null)
  const [dueCount, setDueCount] = useState(0)
  const [error, setError] = useState(null)

  async function refresh() {
    try {
      setError(null)
      setVideos(await listVideos())
    } catch (e) {
      setError(String(e.message || e))
    }
  }
  function refreshDue() {
    getReview().then((r) => setDueCount(r.count)).catch(() => {})
  }

  useEffect(() => {
    refresh()
    refreshDue()
  }, [])

  function openVideo(id) {
    setRevising(false)
    setReviewing(false)
    setStartMs(null)
    setSelected(id)
  }
  function openVideoAt(id, ms) {
    setRevising(false)
    setReviewing(false)
    setStartMs(ms)
    setSelected(id)
  }
  function toLibrary() {
    setRevising(false)
    setReviewing(false)
    setStartMs(null)
    setSelected(null)
    refreshDue()
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="brand" onClick={toLibrary}>écho</h1>
        {(selected || revising) && (
          <button className="link" onClick={toLibrary}>← library</button>
        )}
        <span style={{ flex: 1 }} />
        {!revising && (
          <button className="link" onClick={() => setRevising(true)}>
            revise ({dueCount})
          </button>
        )}
      </header>

      {error && <p className="error">{error}</p>}

      {revising ? (
        <Revise
          onOpen={openVideoAt}
          onBack={() => { setRevising(false); refreshDue() }}
        />
      ) : !selected ? (
        <Library videos={videos} onOpen={openVideo} onChanged={refresh} />
      ) : reviewing ? (
        <Review videoId={selected} onBack={() => setReviewing(false)} />
      ) : (
        <Player videoId={selected} startMs={startMs} onReview={() => setReviewing(true)} />
      )}
    </div>
  )
}
