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

export const runPipeline = (id) =>
  fetch(`/api/videos/${id}/pipeline`, { method: 'POST' }).then(asJson)

export const getIpa = (id) => fetch(`/api/videos/${id}/ipa`).then(asJson)

export const addMark = (id, span, kind, note = null) =>
  fetch(`/api/videos/${id}/marks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ span, kind, note }),
  }).then(asJson)

export const deleteMark = (id, span, kind) =>
  fetch(`/api/videos/${id}/marks/${span[0]}/${span[1]}/${kind}`, {
    method: 'DELETE',
  }).then(asJson)

export const getTranslation = (id, segIdx, lang) =>
  fetch(`/api/videos/${id}/translation/${segIdx}?lang=${lang}`).then(asJson)

export const explainMark = (id, span, force = false) =>
  fetch(`/api/videos/${id}/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ span, force }),
  }).then(asJson)

export const setCardStatus = (cardId, status) =>
  fetch(`/api/cards/${cardId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  }).then(asJson)

export const setLexeme = (lemma, lang, status) =>
  fetch('/api/lexemes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lemma, lang, status }),
  }).then(asJson)
