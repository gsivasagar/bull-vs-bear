/** Server-Sent Events over fetch (EventSource cannot POST or send an API-key header). */

/** Split a text buffer into complete SSE messages; returns { events, rest } where rest is an unfinished tail. */
export function parseSSE(buffer) {
  const events = []
  const blocks = buffer.split('\n\n')
  const rest = blocks.pop() ?? ''
  for (const block of blocks) {
    let event = 'message'
    const data = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
    }
    if (!data.length) continue
    try {
      events.push({ event, data: JSON.parse(data.join('\n')) })
    } catch {
      // ignore a malformed message rather than breaking the whole stream
    }
  }
  return { events, rest }
}

/**
 * POST to the streaming debate endpoint and call onEvent({event, data}) for each message.
 * The API key travels in a header, never in the URL or body. Resolves when the stream ends.
 */
export async function streamDebate({ baseUrl, ticker, apiKey, onEvent, signal, fetchImpl = fetch }) {
  const headers = { 'Content-Type': 'application/json' }
  if (apiKey) headers['X-Api-Key'] = apiKey
  const response = await fetchImpl(`${baseUrl}/api/debate/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ ticker }),
    signal,
  })
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      detail = typeof body.detail === 'string' ? body.detail : body.detail?.[0]?.msg ?? detail
    } catch {
      // keep the generic message
    }
    throw new Error(detail)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const { events, rest } = parseSSE(buffer)
    buffer = rest
    events.forEach(onEvent)
  }
}
