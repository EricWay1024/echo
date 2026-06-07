async function asJson(r) {
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail || detail } catch { /* non-json */ }
    throw new Error(detail)
  }
  return r.json()
}

export const listVideos = () => fetch('/api/videos').then(asJson)

export const getVideo = (id) => fetch(`/api/videos/${id}`).then(asJson)

export const addVideo = (url) =>
  fetch('/api/videos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  }).then(asJson)
