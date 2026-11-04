import { describe, expect, it, vi } from 'vitest'
import { parseSSE, streamDebate } from './sse'

describe('parseSSE', () => {
  it('parses complete messages and keeps the unfinished tail', () => {
    const { events, rest } = parseSSE('event: start\ndata: {"a":1}\n\nevent: stage\ndata: {"b":2}\n\nevent: do')
    expect(events).toEqual([{ event: 'start', data: { a: 1 } }, { event: 'stage', data: { b: 2 } }])
    expect(rest).toBe('event: do')
  })

  it('joins multi-line data and defaults the event name', () => {
    expect(parseSSE('data: {"x":\ndata: 1}\n\n').events).toEqual([{ event: 'message', data: { x: 1 } }])
  })

  it('skips malformed and empty messages instead of throwing', () => {
    expect(parseSSE('event: a\ndata: not json\n\nevent: b\n\nevent: c\ndata: {"ok":true}\n\n').events)
      .toEqual([{ event: 'c', data: { ok: true } }])
  })

  it('returns nothing for an empty buffer', () => {
    expect(parseSSE('')).toEqual({ events: [], rest: '' })
  })
})

const streamOf = (chunks) => {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)))
      controller.close()
    },
  })
}

describe('streamDebate', () => {
  it('sends the key in a header (not the body or URL) and delivers events split across chunks', async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      body: streamOf(['event: start\ndata: {"stages":["a"]}\n\nevent: sta', 'ge\ndata: {"stage":"a"}\n\n']),
    }))
    const seen = []
    await streamDebate({ baseUrl: 'http://x', ticker: 'NVDA', apiKey: 'SECRET', onEvent: (e) => seen.push(e), fetchImpl })
    expect(seen.map((e) => e.event)).toEqual(['start', 'stage'])
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toBe('http://x/api/debate/stream')
    expect(init.headers['X-Api-Key']).toBe('SECRET')
    expect(init.body).toBe('{"ticker":"NVDA"}')
    expect(url + init.body).not.toContain('SECRET')
  })

  it('omits the header when there is no key', async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true, body: streamOf([]) }))
    await streamDebate({ baseUrl: 'http://x', ticker: 'A', apiKey: '', onEvent: () => {}, fetchImpl })
    expect(fetchImpl.mock.calls[0][1].headers['X-Api-Key']).toBeUndefined()
  })

  it('turns an error response into a readable message', async () => {
    const bad = (body, status) => vi.fn(async () => ({ ok: false, status, json: async () => body }))
    await expect(streamDebate({ baseUrl: 'h', ticker: 'A', onEvent: () => {}, fetchImpl: bad({ detail: 'Too many requests.' }, 429) }))
      .rejects.toThrow('Too many requests.')
    await expect(streamDebate({ baseUrl: 'h', ticker: 'A', onEvent: () => {}, fetchImpl: bad({ detail: [{ msg: 'Enter a stock symbol' }] }, 422) }))
      .rejects.toThrow('Enter a stock symbol')
    await expect(streamDebate({ baseUrl: 'h', ticker: 'A', onEvent: () => {}, fetchImpl: vi.fn(async () => ({ ok: false, status: 500, json: async () => { throw new Error('x') } })) }))
      .rejects.toThrow('Request failed (500)')
  })
})
