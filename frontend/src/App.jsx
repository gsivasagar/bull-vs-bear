import { useEffect, useRef, useState } from 'react'
import './App.css'
import ArgumentCard from './components/ArgumentCard'
import VolatilityCard from './components/VolatilityCard'
import { formatMarketCap, formatMoney, formatRatio } from './format'
import { streamDebate } from './sse'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const STAGE_LABELS = {
  fetch_data: 'Fetching market data and news',
  bull_agent: 'The Bull is building the case',
  bear_agent: 'The Bear is building the case',
  judge_agent: 'The Judge is weighing both sides',
}

const DEFAULT_DISCLAIMER =
  'For education and entertainment only. AI-generated from public data; not financial advice.'

// Tokens used by the model calls in this debate (and a cost estimate only when the server has prices configured).
export function UsageLine({ usage }) {
  if (!usage || !usage.calls) return null
  const cost = typeof usage.cost_usd === 'number' ? ` · about $${usage.cost_usd.toFixed(4)}` : ''
  return (
    <p className="usage-line">
      {usage.calls} model calls · {usage.input_tokens.toLocaleString('en-US')} tokens in ·{' '}
      {usage.output_tokens.toLocaleString('en-US')} tokens out{cost}
    </p>
  )
}

function App() {
  const [ticker, setTicker] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [running, setRunning] = useState(false)
  const [stages, setStages] = useState([])        // every step that will run
  const [finished, setFinished] = useState([])    // steps that have finished
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [demoEnabled, setDemoEnabled] = useState(false)
  const [examples, setExamples] = useState([])      // saved real debates that need no key
  const [savedOn, setSavedOn] = useState(null)       // set while a saved example is on screen
  const abortRef = useRef(null)

  // Stop any running debate when the page closes.
  useEffect(() => () => abortRef.current?.abort(), [])

  // Does the server allow a debate without the visitor's own key (demo mode)?
  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE_URL}/api/config`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : {}))
      .then((cfg) => setDemoEnabled(Boolean(cfg.demo_enabled)))
      .catch(() => {})
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE_URL}/api/examples`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : []))
      .then((list) => setExamples(Array.isArray(list) ? list : []))
      .catch(() => {})
    return () => controller.abort()
  }, [])

  const showExample = async (symbol) => {
    if (running) return
    try {
      const res = await fetch(`${API_BASE_URL}/api/examples/${encodeURIComponent(symbol)}`)
      if (!res.ok) throw new Error('That saved example is not available.')
      const saved = await res.json()
      setError(null)
      setStages([])
      setFinished([])
      setData(saved)
      setSavedOn(saved.saved_on || 'an earlier date')
    } catch (err) {
      setError(err.message)
    }
  }

  // Ticker suggestions: wait for a pause in typing and encode the text before putting it in the URL.
  useEffect(() => {
    const query = ticker.trim()
    if (!query) return undefined
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/search?q=${encodeURIComponent(query)}`, { signal: controller.signal })
        if (res.ok) setSuggestions(await res.json())
      } catch {
        // suggestions are a convenience; ignore failures and aborts
      }
    }, 250)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [ticker])

  const handleSearch = async () => {
    const symbol = ticker.trim()
    if (!symbol || running) return
    const isLocal = API_BASE_URL.includes('localhost')

    // The key is optional for a local Ollama setup and required for a hosted deployment.
    if (!isLocal && !apiKey && !demoEnabled) {
      setError('Please enter your Gemini API Key. Ollama is only supported when running the app locally.')
      return
    }

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setRunning(true)
    setSavedOn(null)
    setError(null)
    setData(null)
    setStages([])
    setFinished([])
    setSuggestions([])

    try {
      await streamDebate({
        baseUrl: API_BASE_URL,
        ticker: symbol,
        apiKey,
        signal: controller.signal,
        onEvent: ({ event, data: payload }) => {
          if (event === 'start') setStages(payload.stages)
          else if (event === 'stage') {
            setFinished((done) => [...done, payload.stage])
            setData(payload.result)
          } else if (event === 'done') setData(payload)
          else if (event === 'error') setError(payload.detail)
        },
      })
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message || 'An error occurred while running the debate.')
    } finally {
      setRunning(false)
    }
  }

  const complete = data && data.verdict
  const recommendation = data?.recommendation || 'UNKNOWN'

  return (
    <div className="container">
      <div className="header">
        <h1>Bull vs Bear</h1>
        <p className="subtitle">AI-Powered Investment Debate & Analysis</p>
      </div>

      <div className="search-container">
        <div className="input-group">
          <input
            type="password"
            autoComplete="off"
            placeholder={
              API_BASE_URL.includes('localhost')
                ? 'Gemini API Key (Optional for Local Ollama)'
                : demoEnabled ? 'Gemini API Key (optional: free demo runs are limited)' : 'Gemini API Key (Required for Live Site)'
            }
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="api-input"
          />
        </div>
        <div className="input-group">
          <input
            type="text"
            placeholder="Enter Stock Ticker (e.g. NVDA)"
            value={ticker}
            onChange={(e) => {
              setTicker(e.target.value)
              if (!e.target.value.trim()) setSuggestions([])
            }}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            onBlur={() => setTimeout(() => setSuggestions([]), 200)} // delay so a click on a suggestion registers
          />
          {suggestions.length > 0 && (
            <div className="suggestions-dropdown">
              {suggestions.map((s) => (
                <div
                  key={s.symbol}
                  className="suggestion-item"
                  onClick={() => {
                    setTicker(s.symbol)
                    setSuggestions([])
                  }}
                >
                  <strong>{s.symbol}</strong> - {s.name}
                </div>
              ))}
            </div>
          )}
        </div>
        <button onClick={handleSearch} disabled={running}>
          {running ? 'Analyzing...' : 'Start Debate'}
        </button>
      </div>

      {examples.length > 0 && (
        <p className="examples">
          No key? See a saved real debate:{' '}
          {examples.map((e) => (
            <button key={e.ticker} type="button" className="example-btn" onClick={() => showExample(e.ticker)}>
              {e.ticker}
            </button>
          ))}
        </p>
      )}

      {savedOn && <p className="saved-note">Saved example from {savedOn}, not a live result. Prices and news are as of then.</p>}

      {stages.length > 0 && (
        <ul className="progress-list" aria-live="polite">
          {stages.map((stage) => {
            const state = finished.includes(stage) ? 'done' : running ? 'active' : 'idle'
            return (
              <li key={stage} className={`progress-step ${state}`}>
                {state === 'done' ? '✓' : state === 'active' ? '…' : '•'} {STAGE_LABELS[stage] ?? stage}
              </li>
            )
          })}
        </ul>
      )}

      {error && <div className="error-message" role="alert">{error}</div>}

      {data && (
        <>
          <div className="market-data">
            <div className="data-item">
              <div className="data-label">{data.price_data?.company_name || 'Current Price'}</div>
              <div className="data-value">
                {formatMoney(data.price_data?.current_price, data.price_data?.currency)}
              </div>
            </div>
            <div className="data-item">
              <div className="data-label">Market Cap</div>
              <div className="data-value">{formatMarketCap(data.financials?.market_cap, data.price_data?.currency)}</div>
            </div>
            <div className="data-item">
              <div className="data-label">P/E Ratio</div>
              <div className="data-value">{formatRatio(data.financials?.pe_ratio)}</div>
            </div>
          </div>

          <VolatilityCard quant={data.quant} />

          <div className="dashboard">
            {complete && (
              <div className={`recommendation-badge ${recommendation.toLowerCase()}`}>
                {recommendation === 'UNKNOWN' ? 'UNCLEAR' : recommendation}
              </div>
            )}
            <ArgumentCard title="The Bull Case" type="bull" icon="🐂" content={data.bull_argument} />
            <ArgumentCard title="The Bear Case" type="bear" icon="🐻" content={data.bear_argument} />
            <div className="verdict-section">
              <ArgumentCard title="The Verdict" type="judge" icon="⚖️" content={data.verdict} />
            </div>
            <UsageLine usage={data.usage} />
          </div>
        </>
      )}

      <p className="disclaimer">{data?.disclaimer || DEFAULT_DISCLAIMER}</p>
    </div>
  )
}

export default App
