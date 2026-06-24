/**
 * Shared formatting utilities used across views and components.
 */

/**
 * Normalize a mastery/accuracy value to a 0-100 integer percentage.
 *
 * The backend returns probabilities as floats in [0, 1] and rates (accuracy,
 * mastery_rate) as floats in [0, 1] as well. This function reliably converts
 * either representation to a 0-100 integer.
 *
 * Values already in the 0-100 range (e.g. a pre-formatted percentage) are
 * returned as-is after clamping.
 */
export function normalizePercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return 0
  let num = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(num)) return 0
  // Only treat values in [0, 1] as fractions — anything > 1 is already a
  // percentage (e.g. 85 means 85%, not 8500%).
  if (num >= 0 && num <= 1) num = num * 100
  return Math.round(Math.min(100, Math.max(0, num)))
}

export function formatPercent(value) {
  return `${normalizePercent(value)}%`
}

export function formatDate(value) {
  if (!value) return '未知'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '未知' : d.toLocaleString('zh-CN')
}

export function formatShortDate(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1}/${d.getDate()}`
}
