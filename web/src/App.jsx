import { useEffect, useState } from 'react'
import { listVideos } from './api'
import Library from './Library'
import Player from './Player'
import Review from './Review'

export default function App() {
  const [videos, setVideos] = useState(null)
  const [selected, setSelected] = useState(null)
  const [reviewing, setReviewing] = useState(false)
  const [error, setError] = useState(null)

  async function refresh() {
    try {
      setError(null)
      setVideos(await listVideos())
    } catch (e) {
      setError(String(e.message || e))
    }
  }

  useEffect(() => { refresh() }, [])

  function openVideo(id) {
    setReviewing(false)
    setSelected(id)
  }

  function toLibrary() {
    setReviewing(false)
    setSelected(null)
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="brand" onClick={toLibrary}>écho</h1>
        {selected && (
          <button className="link" onClick={toLibrary}>← library</button>
        )}
      </header>

      {error && <p className="error">{error}</p>}

      {!selected ? (
        <Library videos={videos} onOpen={openVideo} onChanged={refresh} />
      ) : reviewing ? (
        <Review videoId={selected} onBack={() => setReviewing(false)} />
      ) : (
        <Player videoId={selected} onReview={() => setReviewing(true)} />
      )}
    </div>
  )
}
