import { useState } from 'react'
import axios from 'axios'
import './App.css'
import ArgumentCard from './components/ArgumentCard'

function App() {
  const [ticker, setTicker] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [suggestions, setSuggestions] = useState([]) // New state for search suggestions

  const handleSearch = async () => {
    if (!ticker) return
    // API key is now optional for local Ollama usage
    // if (!apiKey) {
    //   setError("Please enter your Gemini API Key")
    //   return
    // }

    setLoading(true)
    setError(null)
    setData(null)

    try {
      // Connects to our FastAPI backend
      const response = await axios.post('http://localhost:8000/api/debate', {
        ticker: ticker,
        api_key: apiKey
      })
      setData(response.data)
    } catch (err) {
      console.error(err)
      setError(err.response?.data?.detail || err.message || 'An error occurred while fetching the debate.')
    } finally {
      setLoading(false)
    }
  }

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
            placeholder="Gemini API Key (Optional for Local)"
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
            onChange={async (e) => {
              const val = e.target.value
              setTicker(val)

              if (val.length > 0) {
                try {
                  const res = await axios.get(`http://localhost:8000/api/search?q=${val}`)
                  setSuggestions(res.data)
                } catch (err) {
                  console.error("Search error", err)
                }
              } else {
                setSuggestions([])
              }
            }}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            onBlur={() => setTimeout(() => setSuggestions([]), 200)} // Delay to allow click
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
        <button onClick={handleSearch} disabled={loading}>
          {loading ? 'Analyzing...' : 'Start Debate'}
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      {data && (
        <>
          <div className="market-data">
            <div className="data-item">
              <div className="data-label">Current Price</div>
              <div className="data-value">${data.price_data.current_price?.toFixed(2)}</div>
            </div>
            <div className="data-item">
              <div className="data-label">Market Cap</div>
              <div className="data-value">{data.financials.market_cap}</div>
            </div>
            <div className="data-item">
              <div className="data-label">P/E Ratio</div>
              <div className="data-value">{data.financials.pe_ratio}</div>
            </div>
          </div>

          <div className="dashboard">
            <div className={`recommendation-badge ${data.recommendation?.toLowerCase()}`}>
              {data.recommendation || "HOLD"}
            </div>
            <ArgumentCard
              title="The Bull Case"
              type="bull"
              icon="🐂"
              content={data.bull_argument}
            />
            <ArgumentCard
              title="The Bear Case"
              type="bear"
              icon="🐻"
              content={data.bear_argument}
            />

            <div className="verdict-section">
              <ArgumentCard
                title="The Verdict"
                type="judge"
                icon="⚖️"
                content={data.verdict}
              />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default App
