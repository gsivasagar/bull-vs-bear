import { describe, expect, it } from 'vitest'
import { formatMarketCap, formatMoney, formatRatio } from './format'

describe('formatMoney', () => {
  it('uses the stock currency', () => {
    expect(formatMoney(12.5, 'USD')).toBe('$12.50')
    expect(formatMoney(12.5, 'EUR')).toContain('€')
    expect(formatMoney(1234.5, 'JPY')).toContain('¥')
  })
  it('falls back safely for missing values and bad codes', () => {
    expect(formatMoney(undefined)).toBe('—')
    expect(formatMoney(NaN)).toBe('—')
    expect(formatMoney(5, 'not-a-code')).toBe('$5.00')
  })
})

describe('formatMarketCap', () => {
  it('shortens large numbers and keeps the currency', () => {
    expect(formatMarketCap(3.2e12, 'USD')).toBe('3.2T USD')
    expect(formatMarketCap(4.5e11, 'GBP')).toBe('450.0B GBP')
    expect(formatMarketCap(1.25e7)).toBe('12.5M USD')
  })
  it('shows a dash when missing', () => {
    expect(formatMarketCap(null)).toBe('—')
    expect(formatMarketCap(0)).toBe('—')
  })
})

describe('formatRatio', () => {
  it('rounds and handles missing', () => {
    expect(formatRatio(31.4159)).toBe('31.42')
    expect(formatRatio(undefined)).toBe('—')
  })
})
