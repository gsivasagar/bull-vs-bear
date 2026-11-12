import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import VolatilityCard from './VolatilityCard'

const quant = {
  as_of: '2026-11-06',
  horizon_trading_days: 21,
  volatility: { method: 'one-year-average', fallback_used: false, forecast_annualized_pct: 31.2, one_sigma_move_over_horizon_pct: 9.0, regime: 'high', percentile_1y: 80 },
  track_record: {
    status: 'ready', test_dates: 30,
    scores: { naive: { qlike: 0.05, rmse_vol_pts: 3 }, long_run: { qlike: 0.03, rmse_vol_pts: 2 } },
    calibration: { inside_1sigma_pct: 67, inside_2sigma_pct: 94 },
    summary: 'Forecast from the one-year-average method.',
  },
  price: { return_1m_pct: 1, return_3m_pct: 2, return_6m_pct: 3, max_drawdown_1y_pct: -10, past_months_up_pct: 55, past_months_up_note: 'past base rate, not a forecast' },
  caveats: ['This forecasts how much the price may move, not which way. No direction forecast is made.'],
}
const render = (q) => renderToStaticMarkup(<VolatilityCard quant={q} />)

describe('VolatilityCard', () => {
  it('renders nothing when the block is missing or has an error', () => {
    expect(render(undefined)).toBe('')
    expect(render({})).toBe('')
    expect(render({ error: 'x', kind: 'failed' })).toBe('')
  })

  it('shows the forecast, regime, summary and the not-a-direction note', () => {
    const html = render(quant)
    expect(html).toContain('31.2%')
    expect(html).toContain('±9.0%')
    expect(html).toContain('Stormy')
    expect(html).toContain('80th percentile')
    expect(html).toContain('Forecast from the one-year-average method.')
    expect(html).toContain('not which way')
  })

  it('keeps model scores and the base rate inside the collapsed details', () => {
    const html = render(quant)
    expect(html).not.toContain('QLIKE')
    expect(html).not.toContain('past base rate')
    expect(html).toContain('Show details')
  })
})
