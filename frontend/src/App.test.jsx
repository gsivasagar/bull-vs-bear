import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { UsageLine } from './App'

describe('UsageLine', () => {
  it('shows tokens, and a cost only when the server sent one', () => {
    const html = renderToStaticMarkup(<UsageLine usage={{ calls: 3, input_tokens: 12345, output_tokens: 678, cost_usd: null }} />)
    expect(html).toContain('3 model calls')
    expect(html).toContain('12,345 tokens in')
    expect(html).not.toContain('$')
    const priced = renderToStaticMarkup(<UsageLine usage={{ calls: 3, input_tokens: 1, output_tokens: 1, cost_usd: 0.00123 }} />)
    expect(priced).toContain('about $0.0012')
  })
  it('renders nothing before any model call', () => {
    expect(renderToStaticMarkup(<UsageLine usage={{ calls: 0, input_tokens: 0, output_tokens: 0, cost_usd: null }} />)).toBe('')
    expect(renderToStaticMarkup(<UsageLine usage={undefined} />)).toBe('')
  })
})
