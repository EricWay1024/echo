import { useEffect, useState } from 'react'
import { listVideos } from './api'
import Library from './Library'
import Player from './Player'

export default function App() {
  const [videos, setVideos] = useState(null)
  const [selected, setSelected] = useState(null)
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

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="brand" onClick={() => setSelected(null)}>écho</h1>
        {selected && (
          <button className="link" onClick={() => setSelected(null)}>← library</button>
        )}
      </header>

      {error && <p className="error">{error}</p>}

      {selected ? (
        <Player videoId={selected} />
      ) : (
        <Library videos={videos} onOpen={setSelected} onChanged={refresh} />
      )}
    </div>
  )
}
