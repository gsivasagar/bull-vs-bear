// Number formatting for the market-data strip. Prices carry the stock's own currency (Yahoo reports it), so a
// London or Tokyo listing is not shown with a dollar sign.

const CURRENCY_CODE = /^[A-Z]{3}$/

export function formatMoney(value, currency = 'USD') {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  const code = CURRENCY_CODE.test(currency || '') ? currency : 'USD'
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: code }).format(value)
  } catch {
    return `${value.toFixed(2)} ${code}`
  }
}

// Market cap as a short figure with its currency: 3.2T, 450.1B, 12.5M.
export function formatMarketCap(value, currency = 'USD') {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return '—'
  const code = CURRENCY_CODE.test(currency || '') ? currency : 'USD'
  const units = [[1e12, 'T'], [1e9, 'B'], [1e6, 'M']]
  for (const [size, suffix] of units) {
    if (value >= size) return `${(value / size).toFixed(1)}${suffix} ${code}`
  }
  return `${value.toLocaleString('en-US', { maximumFractionDigits: 0 })} ${code}`
}

export function formatRatio(value) {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('en-US', { maximumFractionDigits: 2 })
    : '—'
}
