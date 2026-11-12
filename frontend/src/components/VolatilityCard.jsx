import { useState } from 'react'
import './VolatilityCard.css'

const REGIME_LABELS = { low: 'Calm', normal: 'Normal', high: 'Stormy' }
const MODEL_LABELS = { naive: 'Last month repeated (naive)', long_run: 'One-year average', ewma: 'Recent-weighted (EWMA)' }

const pct = (v) => (typeof v === 'number' && Number.isFinite(v) ? `${v.toFixed(1)}%` : '—')
const num = (v, d = 4) => (typeof v === 'number' && Number.isFinite(v) ? v.toFixed(d) : '—')

// Shows the volatility forecast that the agents also see (a size-of-move estimate, not a price or direction forecast).
// The card is hidden when the quant block is missing or carries an error: a debate never depends on it.
const VolatilityCard = ({ quant }) => {
  const [open, setOpen] = useState(false)
  if (!quant || quant.error || !quant.volatility) return null

  const v = quant.volatility
  const t = quant.track_record || {}
  const p = quant.price || {}
  const cal = t.calibration
  const scores = t.scores || {}

  return (
    <section className="volatility-card" aria-label="Volatility forecast">
      <div className="vol-header">
        <h3>Volatility forecast</h3>
        <span className={`vol-regime ${v.regime || 'normal'}`}>{REGIME_LABELS[v.regime] || 'Normal'}</span>
      </div>

      <div className="vol-main">
        <div className="vol-item">
          <div className="vol-label">Expected yearly swing</div>
          <div className="vol-value">{pct(v.forecast_annualized_pct)}</div>
        </div>
        <div className="vol-item">
          <div className="vol-label">Typical move over {quant.horizon_trading_days} trading days (±1σ)</div>
          <div className="vol-value">±{pct(v.one_sigma_move_over_horizon_pct)}</div>
        </div>
        <div className="vol-item">
          <div className="vol-label">Versus its own past year</div>
          <div className="vol-value">{typeof v.percentile_1y === 'number' ? `${v.percentile_1y}th percentile` : '—'}</div>
        </div>
      </div>

      {t.summary && <p className="vol-summary">{t.summary}</p>}
      <p className="vol-note">{quant.caveats?.[0] || 'This estimates how much the price may move, not which way.'}</p>

      <button type="button" className="vol-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {open ? 'Hide details' : 'Show details'}
      </button>

      {open && (
        <div className="vol-details">
          <p className="vol-meta">
            Method: {v.method}
            {v.fallback_used ? ' (fallback used)' : ''} · as of {quant.as_of || 'unknown'}
          </p>

          {t.status === 'ready' && (
            <>
              <table className="vol-table">
                <thead>
                  <tr><th>Method</th><th>Error (QLIKE, lower is better)</th><th>Error (vol points)</th></tr>
                </thead>
                <tbody>
                  {Object.entries(scores).map(([name, s]) => (
                    <tr key={name}>
                      <td>{MODEL_LABELS[name] || name}</td>
                      <td>{num(s.qlike)}</td>
                      <td>{num(s.rmse_vol_pts, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {cal && (
                <p className="vol-meta">
                  Over {t.test_dates} past months, real moves stayed inside ±1σ {pct(cal.inside_1sigma_pct)} of the time
                  (about 68% expected) and inside ±2σ {pct(cal.inside_2sigma_pct)} (about 95% expected).
                </p>
              )}
            </>
          )}

          <p className="vol-meta">
            Recent price moves: 1 month {pct(p.return_1m_pct)}, 3 months {pct(p.return_3m_pct)}, 6 months{' '}
            {pct(p.return_6m_pct)}; worst fall in the last year {pct(p.max_drawdown_1y_pct)}.
          </p>
          {typeof p.past_months_up_pct === 'number' && (
            <p className="vol-meta">
              Share of past months with a rise: {p.past_months_up_pct}% ({p.past_months_up_note || 'past base rate, not a forecast'}).
            </p>
          )}
        </div>
      )}
    </section>
  )
}

export default VolatilityCard
