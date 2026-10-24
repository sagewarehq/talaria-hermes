/** From a query's result to what charts draw: typed rows, series, scales and formatted values. */
import { headerText, isNumericType, isTemporalType, type QueryResult } from './db.ts'
import type { Format, Row } from './types.ts'

/* --------------------------------------------------------------- values */

/** A source's text for a date or time ("2026-01-05", "2026-01-05 09:30:00+08", "2026-01-05T01:30:00Z") as a Date. Dates are local midnight. */
export function parseTemporal(s: string): Date | null {
  const m = /^(\d{4})-(\d\d)-(\d\d)(?:[ T](\d\d):(\d\d)(?::(\d\d)(?:\.(\d+))?)?)?\s*(Z|[+-]\d\d(?::?\d\d)?)?$/.exec(s.trim())
  if (!m) return null
  const [, y, mo, d, h = '0', mi = '0', sec = '0', frac = '0', tz] = m
  const ms = Number(frac.slice(0, 3).padEnd(3, '0'))
  if (!tz) return new Date(+y, +mo - 1, +d, +h, +mi, +sec, ms)
  const off = tz === 'Z' ? 0 : (tz[0] === '-' ? -1 : 1) * (Number(tz.slice(1, 3)) * 60 + Number(tz.replace(':', '').slice(3, 5) || 0))
  return new Date(Date.UTC(+y, +mo - 1, +d, +h, +mi, +sec, ms) - off * 60_000)
}

/** Result rows as objects, with numbers as numbers and dates as Dates (by their column's type). */
export function toRows(result: QueryResult): Row[] {
  const conv = result.columns.map((c) =>
    isNumericType(c.type) ? (v: unknown) => (v === null ? null : Number(v)) : isTemporalType(c.type) ? (v: unknown) => (typeof v === 'string' ? (parseTemporal(v) ?? v) : v) : (v: unknown) => v,
  )
  return result.rows.map((r) => Object.fromEntries(result.columns.map((c, i) => [c.name, conv[i](r[i])])))
}

export type ValueKind = 'number' | 'time' | 'category'

/** What a column holds, from its values. */
export function kindOfValues(rows: Row[], key: string): ValueKind {
  let numbers = 0
  let dates = 0
  let seen = 0
  for (const r of rows) {
    const v = r[key]
    if (v === null || v === undefined) continue
    seen++
    if (typeof v === 'number') numbers++
    else if (v instanceof Date) dates++
  }
  if (!seen) return 'category'
  return dates === seen ? 'time' : numbers === seen ? 'number' : 'category'
}

/** The format a column gets when nothing says otherwise. */
export function defaultFormat(rows: Row[], key: string, type?: string): Format {
  if (type && isTemporalType(type) && !/^time\b/.test(type)) {
    const ds = rows.map((r) => r[key]).filter((v): v is Date => v instanceof Date)
    if (ds.length && ds.every((d) => d.getDate() === 1 && d.getHours() === 0 && d.getMinutes() === 0)) return 'month'
    return ds.every((d) => d.getHours() === 0 && d.getMinutes() === 0) ? 'date' : 'text'
  }
  const kind = kindOfValues(rows, key)
  if (kind === 'time') return 'date'
  if (kind === 'number') return rows.every((r) => typeof r[key] !== 'number' || Number.isInteger(r[key])) ? 'integer' : 'number'
  return 'text'
}

const nf = new Map<string, Intl.NumberFormat>()
const num = (opts: Intl.NumberFormatOptions) => {
  const k = JSON.stringify(opts)
  if (!nf.has(k)) nf.set(k, new Intl.NumberFormat(undefined, opts))
  return nf.get(k)!
}

/** Each column's format: the one given, else one from its type and values. */
export function formatsFor(rows: Row[], keys: string[], types: Record<string, string>, given?: Record<string, Format>): Record<string, Format> {
  return Object.fromEntries(keys.map((k) => [k, given?.[k] ?? defaultFormat(rows, k, types[k])]))
}

export function formatValue(v: unknown, format: Format | undefined): string {
  if (v === null || v === undefined) return '—'
  if (v instanceof Date) {
    if (format === 'month') return v.toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
    if (format === 'date' || v.getHours() + v.getMinutes() + v.getSeconds() === 0) return v.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    return v.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
  }
  if (typeof v === 'number') {
    if (typeof format === 'object') return 'currency' in format ? num({ style: 'currency', currency: format.currency }).format(v) : String(v)
    switch (format) {
      case 'integer':
        return num({ maximumFractionDigits: 0 }).format(v)
      case 'compact':
        return num({ notation: 'compact', maximumFractionDigits: 1 }).format(v)
      case 'currency':
        return num({ style: 'currency', currency: 'USD' }).format(v)
      case 'percent':
        return num({ style: 'percent', maximumFractionDigits: 1 }).format(v)
      case 'text':
        return String(v)
      default:
        return num({ maximumFractionDigits: 2 }).format(v)
    }
  }
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

/** For axis ticks: shorter than formatValue (compact numbers, no decimals where they don't matter). */
/**
 * Where a value with a `{ link }` format points: a link type from a studio.json (or datagen.json) in its folder or above, or a URL with {value}.
 * Other `{name}`s are filled from the same row's columns (`{branch}`); a link missing one isn't made.
 */
export function linkHref(v: unknown, format: Format | undefined, links: Record<string, string> | undefined, row: Row = {}): string | undefined {
  if (v === null || v === undefined || typeof format !== 'object' || !('link' in format)) return undefined
  const template = format.link.includes('{value}') ? format.link : links?.[format.link]
  // A URL elsewhere, or a visualization in projects/ ("VCM/patients/patient.viz.tsx?patient={value}"), opened in the app.
  const inApp = template && VIZ_LINK.exec(template)
  if (!template || !(inApp || /^https?:\/\//i.test(template))) return undefined
  const text = (x: unknown) => encodeURIComponent(String(x instanceof Date ? x.toISOString() : x))
  let missing = false
  const fill = (t: string) =>
    t.replace(/\{(\w+)\}/g, (_, name: string) => {
      const x = name === 'value' ? v : row[name]
      if (x === null || x === undefined || x === '') missing = true
      return text(x)
    })
  const href = inApp ? `#/d/${inApp[1].replace(/^\/+/, '').split('/').map(encodeURIComponent).join('/')}${inApp[2] ? fill(inApp[2]) : ''}` : fill(template)
  return missing ? undefined : href
}

/** A link type that names a visualization by its path in projects/, with `?name={value}` for its params. */
const VIZ_LINK = /^([^:?#]+\.viz\.tsx)(\?.*)?$/

export function formatTick(v: number | Date, format: Format | undefined, span: number): string {
  if (v instanceof Date) {
    const day = 86_400_000
    if (format === 'month' || span > 120 * day) return v.toLocaleDateString(undefined, span > 2 * 365 * day ? { year: 'numeric' } : { month: 'short', year: '2-digit' })
    if (span > 2 * day) return v.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    return v.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  }
  if (format === 'percent') return num({ style: 'percent', maximumFractionDigits: 0 }).format(v)
  const currency = typeof format === 'object' && 'currency' in format ? format.currency : format === 'currency' ? 'USD' : undefined
  if (Math.abs(v) >= 10_000) return num({ notation: 'compact', maximumFractionDigits: 1, ...(currency && { style: 'currency', currency }) }).format(v)
  return num({ maximumFractionDigits: Math.abs(v) < 10 && !Number.isInteger(v) ? 2 : 0, ...(currency && { style: 'currency', currency }) }).format(v)
}

/* --------------------------------------------------------------- series */

export const MAX_SERIES = 8

export interface Series {
  key: string
  /** What it's called on the chart: a y column's name in words ("returned_30_days" → "Returned 30 days"), or a value as it is. */
  label: string
  /** Its color slot, 1 to 8, in order of first appearance, so a series keeps its color. */
  slot: number
  /** y values by x key. */
  values: Map<string, number>
}

export interface XValue {
  key: string
  value: unknown
}

const keyOf = (v: unknown) => (v instanceof Date ? String(v.getTime()) : String(v))

/**
 * Rows as series along x: one per y column, or with `series`, one per value of that column. More than eight are
 * folded: the seven largest stay and the rest add up to "Other".
 */
export function buildSeries(rows: Row[], x: string, y: string | string[], series?: string): { xs: XValue[]; series: Series[] } {
  const ys = Array.isArray(y) ? y : [y]
  const xs: XValue[] = []
  const seenX = new Set<string>()
  const byKey = new Map<string, Map<string, number>>()
  const add = (s: string, xk: string, v: unknown) => {
    if (typeof v !== 'number' || Number.isNaN(v)) return
    if (!byKey.has(s)) byKey.set(s, new Map())
    const m = byKey.get(s)!
    m.set(xk, (m.get(xk) ?? 0) + v)
  }
  for (const r of rows) {
    const xv = r[x]
    if (xv === null || xv === undefined) continue
    const xk = keyOf(xv)
    if (!seenX.has(xk)) {
      seenX.add(xk)
      xs.push({ key: xk, value: xv })
    }
    if (series) add(String(r[series] ?? '—'), xk, r[ys[0]])
    else for (const yk of ys) add(yk, xk, r[yk])
  }
  let list: Series[] = [...byKey.entries()].map(([key, values], i) => ({ key, label: series ? key : headerText(key), slot: i + 1, values }))
  if (list.length > MAX_SERIES) {
    const total = (s: Series) => [...s.values.values()].reduce((a, b) => a + Math.abs(b), 0)
    const kept = [...list].sort((a, b) => total(b) - total(a)).slice(0, MAX_SERIES - 1)
    const keptKeys = new Set(kept.map((s) => s.key))
    const other = new Map<string, number>()
    for (const s of list) if (!keptKeys.has(s.key)) for (const [k, v] of s.values) other.set(k, (other.get(k) ?? 0) + v)
    // Kept series keep the order they appeared in; their slots follow it.
    list = [...list.filter((s) => keptKeys.has(s.key)).map((s, i) => ({ ...s, slot: i + 1 })), { key: 'Other', label: 'Other', slot: MAX_SERIES, values: other }]
  }
  return { xs, series: list }
}

/* ---------------------------------------------------------------- scales */

/** Round tick values covering [min, max]: 0, 250, 500, … */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (min === max) {
    if (min === 0) return [0, 1]
    ;[min, max] = min > 0 ? [0, max] : [min, 0]
  }
  const raw = (max - min) / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag
  const start = Math.floor(min / step) * step
  const ticks: number[] = []
  for (let v = start; v < max + step * 0.999; v += step) ticks.push(Number(v.toFixed(10)))
  return ticks
}

/** Ticks for a time axis: about `count` round dates (months, days or hours) inside [min, max]. */
export function timeTicks(min: number, max: number, count = 6): Date[] {
  const span = max - min
  const day = 86_400_000
  const out: Date[] = []
  if (span > 60 * day) {
    const months = span / (30 * day)
    const every = [1, 2, 3, 6, 12, 24, 60].find((m) => months / m <= count) ?? 120
    const d = new Date(min)
    d.setDate(1)
    d.setHours(0, 0, 0, 0)
    if (d.getTime() < min) d.setMonth(d.getMonth() + 1)
    while (d.getMonth() % every !== 0 && every <= 12) d.setMonth(d.getMonth() + 1)
    for (; d.getTime() <= max; d.setMonth(d.getMonth() + every)) out.push(new Date(d))
  } else {
    const steps = [3_600_000, 3 * 3_600_000, 6 * 3_600_000, 12 * 3_600_000, day, 2 * day, 7 * day, 14 * day]
    const every = steps.find((s) => span / s <= count) ?? 30 * day
    const d = new Date(min)
    d.setMinutes(0, 0, 0)
    if (every >= day) d.setHours(0)
    let t = d.getTime()
    while (t < min) t += every
    for (; t <= max; t += every) out.push(new Date(t))
  }
  return out
}

export const linear = (d0: number, d1: number, r0: number, r1: number) => (v: number) => (d1 === d0 ? (r0 + r1) / 2 : r0 + ((v - d0) / (d1 - d0)) * (r1 - r0))
