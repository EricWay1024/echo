import { useState } from 'react'
import { addVideo } from './api'

function fmtDur(ms) {
  if (!ms) return ''
  const s = Math.round(ms / 1000)
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

export default function Library({ videos, onOpen, onChanged }) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function add(e) {
    e.preventDefault()
    if (!url.trim()) return
    setBusy(true)
    setErr(null)
    try {
      await addVideo(url.trim())
      setUrl('')
      onChanged()
    } catch (e) {
      setErr(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="library">
      <form className="add" onSubmit={add}>
        <input
          type="url"
          placeholder="paste a YouTube URL…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={busy}
        />
        <button disabled={busy || !url.trim()}>{busy ? 'fetching…' : 'add'}</button>
      </form>
      {err && <p className="error">{err}</p>}

      {videos === null && <p className="muted">loading…</p>}
      {videos && videos.length === 0 && (
        <p className="muted">no videos yet — add one above.</p>
      )}

      <ul className="videolist">
        {videos &&
          videos.map((v) => (
            <li key={v.id} onClick={() => onOpen(v.id)}>
              <span className="vtitle">{v.title || v.id}</span>
              <span className="vmeta">
                {v.channel}
                {v.duration_ms ? ` · ${fmtDur(v.duration_ms)}` : ''}
                {v.status === 'pipelined' ? ' · ✓ rectified' : ''}
              </span>
            </li>
          ))}
      </ul>
    </main>
  )
}
