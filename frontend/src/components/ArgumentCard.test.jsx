import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import ArgumentCard from './ArgumentCard'

const render = (content) => renderToStaticMarkup(<ArgumentCard title="T" type="bull" icon="x" content={content} />)

describe('ArgumentCard renders untrusted model text safely', () => {
  it('does not turn HTML in the text into elements', () => {
    const html = render('Hello <img src=x onerror="alert(1)"> and <script>alert(2)</script> <b onclick="x()">bold</b>')
    expect(html).not.toMatch(/<img/i)
    expect(html).not.toMatch(/<script/i)
    expect(html).not.toMatch(/<[a-z][^>]*\son(error|click)\s*=/i)   // no real tag carries an event handler
    expect(html).toContain('&lt;img')                                   // the text is shown, harmlessly escaped
  })

  it('removes images that Markdown itself can produce (tracking pixels)', () => {
    expect(render('![pixel](https://evil.example/p.gif)')).not.toMatch(/<img/i)
  })

  it('blocks javascript: links and opens real links safely', () => {
    expect(render('[click](javascript:alert(1))')).not.toMatch(/href="javascript:/i)
    const ok = render('[site](https://example.com)')
    expect(ok).toContain('href="https://example.com"')
    expect(ok).toContain('rel="noopener noreferrer nofollow"')
    expect(ok).toContain('target="_blank"')
  })

  it('renders Markdown and shows a placeholder when empty', () => {
    expect(render('**Verdict**: BUY')).toContain('<strong>Verdict</strong>')
    expect(render('')).toContain('Waiting for analysis')
    expect(render(undefined)).toContain('Waiting for analysis')
  })
})
