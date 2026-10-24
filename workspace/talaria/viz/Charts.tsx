import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Chart, Format, Row } from './types.ts'
import { buildSeries, formatTick, formatValue, kindOfValues, linear, niceTicks, timeTicks, type Series } from './data.ts'

/**
 * The charts a panel draws, in SVG: line, area, bar, scatter, a headline number. Marks are thin and quiet (2px lines,
 * bars at most 24px with a rounded data end, hairline grids); color says which series, in fixed slot order, and two or
 * more series always get a legend. Hovering shows the values.
 */

export interface ChartProps {
  chart: Chart
  rows: Row[]
  /** Formats by column (from the panel, else from the column types). */
  formats: Record<string, Format>
  height: number
}

const color = (slot: number) => `var(--series-${slot})`

function useWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)))
    ro.observe(el)
    setWidth(Math.floor(el.getBoundingClientRect().width))
    return () => ro.disconnect()
  }, [])
  return { ref, width }
}

/** Characters → px, for laying out axis labels before they're drawn (12px system sans). */
const textWidth = (s: string) => s.length * 6.6

export function ChartView({ chart, rows, formats, height }: ChartProps) {
  if (!rows.length) return <p className="viz-empty">No rows.</p>
  switch (chart.type) {
    case 'number':
      return <NumberTile chart={chart} rows={rows} formats={formats} />
    case 'line':
    case 'area':
    case 'bar':
      return chart.type === 'bar' && chart.horizontal ? <HBarChart chart={chart} rows={rows} formats={formats} height={height} /> : <XYChart chart={chart} rows={rows} formats={formats} height={height} />
    case 'scatter':
      return <ScatterChart chart={chart} rows={rows} formats={formats} height={height} />
    default:
      return null
  }
}

/* ------------------------------------------------------------------ legend */

function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null
  return (
    <ul className="viz-legend">
      {series.map((s) => (
        <li key={s.key}>
          <span className="viz-swatch" style={{ background: color(s.slot) }} />
          {s.label}
        </li>
      ))}
    </ul>
  )
}

/* ----------------------------------------------------------------- tooltip */

function Tooltip({ x, y, width, title, items }: { x: number; y: number; width: number; title: string; items: { key: string; slot?: number; value: string }[] }) {
  // Beside the pointer, flipped to the other side near the right edge.
  const left = x > width - 200 ? undefined : x + 14
  const right = x > width - 200 ? width - x + 14 : undefined
  return (
    <div className="viz-tooltip" style={{ left, right, top: Math.max(0, y - 10) }}>
      <div className="viz-tooltip-title">{title}</div>
      {items.map((it) => (
        <div key={it.key} className="viz-tooltip-row">
          {it.slot !== undefined && <span className="viz-swatch" style={{ background: color(it.slot) }} />}
          <span className="viz-tooltip-key">{it.key}</span>
          <span className="viz-tooltip-value">{it.value}</span>
        </div>
      ))}
    </div>
  )
}

/* -------------------------------------------------------------------- axes */

interface YAxis {
  ticks: number[]
  scale: (v: number) => number
  label: (v: number) => string
  width: number
}

function yAxis(min: number, max: number, top: number, bottom: number, format: Format | undefined, zero: boolean): YAxis {
  const lo = zero ? Math.min(0, min) : min
  const hi = zero ? Math.max(0, max) : max
  const ticks = niceTicks(lo, hi, Math.max(2, Math.min(6, Math.floor((bottom - top) / 48))))
  const scale = linear(ticks[0], ticks[ticks.length - 1], bottom, top)
  const label = (v: number) => formatTick(v, format, 0)
  return { ticks, scale, label, width: Math.max(...ticks.map((t) => textWidth(label(t)))) + 10 }
}

function Grid({ y, left, right }: { y: YAxis; left: number; right: number }) {
  return (
    <g className="viz-grid">
      {y.ticks.map((t) => (
        <g key={t}>
          <line x1={left} x2={right} y1={y.scale(t)} y2={y.scale(t)} className={t === 0 ? 'viz-baseline' : undefined} />
          <text x={left - 8} y={y.scale(t)} dy="0.32em" textAnchor="end">
            {y.label(t)}
          </text>
        </g>
      ))}
    </g>
  )
}

/** Bottom labels that fit: every nth, so none overlap. */
function XLabels({ items, y }: { items: { x: number; label: string }[]; y: number }) {
  if (!items.length) return null
  const gap = items.length > 1 ? Math.abs(items[1].x - items[0].x) : Infinity
  const widest = Math.max(...items.map((i) => textWidth(i.label))) + 12
  const every = Math.max(1, Math.ceil(widest / gap))
  return (
    <g className="viz-xlabels">
      {items.map((it, i) =>
        i % every === 0 ? (
          <text key={i} x={it.x} y={y} textAnchor="middle">
            {it.label}
          </text>
        ) : null,
      )}
    </g>
  )
}

/* ------------------------------------------------------- line, area, bar */

/** A rect with its data end (top for positive values, bottom for negative) rounded 4px. */
function barPath(x: number, w: number, y0: number, y1: number, round = true) {
  const r = round ? Math.min(4, w / 2, Math.abs(y1 - y0)) : 0
  if (y1 <= y0) return `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + r}V${y0}Z`
  return `M${x},${y0}V${y1 - r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 - r}V${y0}Z`
}

function XYChart({ chart, rows, formats, height }: ChartProps & { chart: Extract<Chart, { type: 'line' | 'area' | 'bar' }> }) {
  const { ref, width } = useWidth()
  const [hover, setHover] = useState<{ i: number; px: number; py: number } | null>(null)
  const { xs, series } = useMemo(() => buildSeries(rows, chart.x, chart.y, chart.series), [rows, chart])
  const yKey = Array.isArray(chart.y) ? chart.y[0] : chart.y
  const yFormat = formats[yKey]
  const xFormat = formats[chart.x]
  const bar = chart.type === 'bar'
  const stacked = (chart.type === 'bar' || chart.type === 'area') && !!chart.stacked && series.length > 1
  const xKind = bar ? 'category' : kindOfValues(rows, chart.x)

  // Values at each x, stacked when asked (each series sitting on the ones before it).
  const stacks = useMemo(() => {
    const base = new Map<string, number>()
    return series.map((s) =>
      xs.map((x) => {
        const v = s.values.get(x.key)
        const b = stacked ? (base.get(x.key) ?? 0) : 0
        if (stacked && v !== undefined) base.set(x.key, b + v)
        return v === undefined ? null : { y0: b, y1: b + v }
      }),
    )
  }, [series, xs, stacked])

  const all = stacks.flat().filter((v): v is { y0: number; y1: number } => !!v)
  const min = Math.min(...all.map((v) => Math.min(v.y0, v.y1)))
  const max = Math.max(...all.map((v) => Math.max(v.y0, v.y1)))
  const top = 10
  const bottom = height - 26
  const zero = chart.type !== 'line' || min <= 0 || min < max * 0.35
  const y = yAxis(min, max, top, bottom, yFormat, zero)
  // Room at the right for labels at the ends of up to four lines, when they all end at the last x: a line that stops
  // early would have its label run over the others (the legend says which is which instead).
  const lastAt = (si: number) => stacks[si].findLastIndex((v) => !!v)
  const endLabels = chart.type !== 'bar' && series.length > 1 && series.length <= 4 && series.every((_, si) => lastAt(si) === xs.length - 1)
  const left = y.width
  const right = width - (endLabels ? Math.min(110, Math.max(...series.map((s) => textWidth(s.label))) + 16) : 12)

  // x positions: bands for bars and categories, a time or number scale otherwise.
  const band = (right - left) / Math.max(1, xs.length)
  let xAt: (i: number) => number
  let xTicks: { x: number; label: string }[]
  if (xKind === 'time' || xKind === 'number') {
    const vals = xs.map((x) => (x.value instanceof Date ? x.value.getTime() : Number(x.value)))
    const lo = Math.min(...vals)
    const hi = Math.max(...vals)
    const sx = linear(lo, hi, left + 4, right - 4)
    xAt = (i) => sx(vals[i])
    xTicks =
      xKind === 'time'
        ? timeTicks(lo, hi, Math.max(2, Math.floor((right - left) / 90))).map((d) => ({ x: sx(d.getTime()), label: formatTick(d, xFormat, hi - lo) }))
        : niceTicks(lo, hi, Math.max(2, Math.floor((right - left) / 80)))
            .filter((t) => t >= lo && t <= hi)
            .map((t) => ({ x: sx(t), label: formatTick(t, xFormat, 0) }))
  } else {
    xAt = (i) => left + band * (i + 0.5)
    xTicks = xs.map((x, i) => ({ x: xAt(i), label: formatValue(x.value, xFormat) }))
  }

  const nearest = (px: number) => {
    let best = 0
    for (let i = 1; i < xs.length; i++) if (Math.abs(xAt(i) - px) < Math.abs(xAt(best) - px)) best = i
    return best
  }

  const path = (pts: ({ x: number; y: number } | null)[]) => {
    let d = ''
    let pen = false
    for (const p of pts) {
      if (!p) {
        pen = false
        continue
      }
      d += `${pen ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`
      pen = true
    }
    return d
  }

  // Bars: grouped side by side in each band (each ≤24px, 2px apart), or one stacked bar.
  const groups = stacked ? 1 : series.length
  const barW = Math.max(2, Math.min(24, (band * 0.72 - (groups - 1) * 2) / groups))
  const groupW = barW * groups + (groups - 1) * 2
  // Single-series bars carry their value at the tip, when there's room.
  const tipLabels = bar && series.length === 1 && xs.length <= 16 && band > 34

  // Line end labels, nudged apart so they don't overlap.
  const ends = endLabels
    ? (() => {
        const items = series
          .map((s, si) => {
            const last = lastAt(si)
            return last < 0 ? null : { s, x: xAt(last), y: y.scale(stacks[si][last]!.y1) }
          })
          .filter((v): v is { s: Series; x: number; y: number } => !!v)
          .sort((a, b) => a.y - b.y)
        for (let i = 1; i < items.length; i++) if (items[i].y - items[i - 1].y < 14) items[i].y = items[i - 1].y + 14
        return items
      })()
    : []

  const hoverItems = (i: number) =>
    series
      .map((s, si) => ({ key: s.key, slot: s.slot, raw: stacks[si][i] ? stacks[si][i]!.y1 - stacks[si][i]!.y0 : undefined }))
      .filter((it) => it.raw !== undefined)
      .map((it) => ({ key: it.key, slot: series.length > 1 ? it.slot : undefined, value: formatValue(it.raw, yFormat) }))

  return (
    <div className="viz-chart">
      <Legend series={series} />
      <div ref={ref} className="viz-plot" style={{ height }}>
        {width > 0 && (
          <svg
            width={width}
            height={height}
            onPointerMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect()
              const px = e.clientX - r.left
              if (px < left - 4 || px > right + 4) return setHover(null)
              setHover({ i: bar ? Math.max(0, Math.min(xs.length - 1, Math.floor((px - left) / band))) : nearest(px), px, py: e.clientY - r.top })
            }}
            onPointerLeave={() => setHover(null)}
          >
            <Grid y={y} left={left} right={right} />
            {bar && hover && <rect className="viz-band-hover" x={left + band * hover.i} y={top} width={band} height={bottom - top} />}
            {bar
              ? series.map((s, si) => (
                  <g key={s.key} fill={color(s.slot)}>
                    {xs.map((x, i) => {
                      const v = stacks[si][i]
                      if (!v) return null
                      const bx = xAt(i) - groupW / 2 + (stacked ? 0 : si * (barW + 2))
                      // In a stack, segments sit 2px apart and only the outermost gets the rounded end.
                      const isTop = !stacked || !stacks.slice(si + 1).some((st) => st[i] && st[i]!.y1 !== st[i]!.y0)
                      const y0 = y.scale(v.y0) - (stacked && si > 0 ? (v.y1 >= v.y0 ? 1 : -1) : 0)
                      const y1 = y.scale(v.y1) + (stacked && !isTop ? (v.y1 >= v.y0 ? 1 : -1) : 0)
                      if (Math.abs(y1 - y0) < 0.5) return null
                      return <path key={x.key} d={barPath(bx, barW, y0, y1, isTop)} />
                    })}
                  </g>
                ))
              : series.map((s, si) => {
                  const pts = stacks[si].map((v, i) => (v ? { x: xAt(i), y: y.scale(v.y1) } : null))
                  const floor = stacks[si].map((v, i) => (v ? { x: xAt(i), y: y.scale(v.y0) } : null))
                  return (
                    <g key={s.key}>
                      {chart.type === 'area' && <path className="viz-area" d={`${path(pts)}${path([...floor].reverse()).replace(/^M/, 'L')}Z`} fill={color(s.slot)} />}
                      <path className="viz-line" d={path(pts)} stroke={color(s.slot)} />
                      {xs.length === 1 && pts[0] && <circle className="viz-dot" cx={pts[0].x} cy={pts[0].y} r={4} fill={color(s.slot)} />}
                    </g>
                  )
                })}
            {tipLabels &&
              xs.map((x, i) => {
                const v = stacks[0][i]
                if (!v) return null
                const up = v.y1 >= 0
                return (
                  <text key={x.key} className="viz-value" x={xAt(i)} y={y.scale(v.y1) + (up ? -6 : 14)} textAnchor="middle">
                    {formatTick(v.y1 - v.y0, yFormat, 0)}
                  </text>
                )
              })}
            {ends.map((e) => (
              <text key={e.s.key} className="viz-end-label" x={e.x + 8} y={e.y} dy="0.32em">
                {e.s.label}
              </text>
            ))}
            {!bar && hover && (
              <g className="viz-crosshair">
                <line x1={xAt(hover.i)} x2={xAt(hover.i)} y1={top} y2={bottom} />
                {series.map((s, si) => {
                  const v = stacks[si][hover.i]
                  return v ? <circle key={s.key} className="viz-dot" cx={xAt(hover.i)} cy={y.scale(v.y1)} r={4} fill={color(s.slot)} /> : null
                })}
              </g>
            )}
            <XLabels items={xTicks} y={height - 8} />
          </svg>
        )}
        {hover && width > 0 && <Tooltip x={hover.px} y={hover.py} width={width} title={formatValue(xs[hover.i].value, xFormat)} items={hoverItems(hover.i)} />}
      </div>
    </div>
  )
}

/* --------------------------------------------------------- horizontal bars */

function HBarChart({ chart, rows, formats, height }: ChartProps & { chart: Extract<Chart, { type: 'bar' }> }) {
  const { ref, width } = useWidth()
  const [hover, setHover] = useState<{ i: number; px: number; py: number } | null>(null)
  const { xs, series } = useMemo(() => buildSeries(rows, chart.x, chart.y, chart.series), [rows, chart])
  const yKey = Array.isArray(chart.y) ? chart.y[0] : chart.y
  const vFormat = formats[yKey]
  const stacked = !!chart.stacked && series.length > 1
  const groups = stacked ? 1 : series.length
  const thick = Math.min(24, Math.max(8, 18 / Math.sqrt(groups)))
  const rowH = groups * thick + (groups - 1) * 2 + 12
  // As tall as its rows need (the panel's height is the least).
  const plotH = Math.max(height, xs.length * rowH + 30)
  const labels = xs.map((x) => formatValue(x.value, formats[chart.x]))
  const labelW = Math.min(180, Math.max(...labels.map(textWidth)) + 12)
  const totals = xs.map((x) => series.map((s) => s.values.get(x.key) ?? 0))
  const max = Math.max(0, ...totals.map((t) => (stacked ? t.reduce((a, b) => a + b, 0) : Math.max(...t))))
  const min = Math.min(0, ...totals.flat())
  const left = labelW
  const right = width - 56
  const ticks = niceTicks(min, max, Math.max(2, Math.floor((right - left) / 90)))
  const sx = linear(ticks[0], ticks[ticks.length - 1], left, right)
  const trunc = (s: string) => (textWidth(s) > labelW - 12 ? `${s.slice(0, Math.floor((labelW - 24) / 6.6))}…` : s)

  return (
    <div className="viz-chart">
      <Legend series={series} />
      <div ref={ref} className="viz-plot" style={{ height: plotH }}>
        {width > 0 && (
          <svg
            width={width}
            height={plotH}
            onPointerMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect()
              const i = Math.floor((e.clientY - r.top - 4) / rowH)
              setHover(i >= 0 && i < xs.length ? { i, px: e.clientX - r.left, py: e.clientY - r.top } : null)
            }}
            onPointerLeave={() => setHover(null)}
          >
            <g className="viz-grid">
              {ticks.map((t) => (
                <g key={t}>
                  <line x1={sx(t)} x2={sx(t)} y1={4} y2={plotH - 22} className={t === 0 ? 'viz-baseline' : undefined} />
                  <text x={sx(t)} y={plotH - 6} textAnchor="middle">
                    {formatTick(t, vFormat, 0)}
                  </text>
                </g>
              ))}
            </g>
            {hover && <rect className="viz-band-hover" x={0} y={4 + hover.i * rowH} width={width} height={rowH} />}
            {xs.map((x, i) => {
              const y0 = 4 + i * rowH + 6
              let acc = 0
              return (
                <g key={x.key}>
                  <text className="viz-cat-label" x={labelW - 10} y={y0 + (rowH - 12) / 2} dy="0.32em" textAnchor="end">
                    {trunc(labels[i])}
                    <title>{labels[i]}</title>
                  </text>
                  {series.map((s, si) => {
                    const v = s.values.get(x.key)
                    if (v === undefined) return null
                    const from = stacked ? acc : 0
                    acc += stacked ? v : 0
                    const to = from + v
                    const by = stacked ? y0 + (rowH - 12 - thick) / 2 : y0 + si * (thick + 2)
                    const isEnd = !stacked || si === series.length - 1 || series.slice(si + 1).every((o) => !o.values.get(x.key))
                    const xa = sx(from) + (stacked && si > 0 ? 1 : 0)
                    const xb = sx(to) - (stacked && !isEnd ? 1 : 0)
                    if (xb - xa < 0.5) return null
                    const r = isEnd ? Math.min(4, thick / 2, xb - xa) : 0
                    return (
                      <path
                        key={s.key}
                        fill={color(s.slot)}
                        d={`M${xa},${by}H${xb - r}Q${xb},${by} ${xb},${by + r}V${by + thick - r}Q${xb},${by + thick} ${xb - r},${by + thick}H${xa}Z`}
                      />
                    )
                  })}
                  {series.length === 1 && (
                    <text className="viz-value" x={sx(totals[i][0]) + 6} y={y0 + thick / 2} dy="0.32em">
                      {formatTick(totals[i][0], vFormat, 0)}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
        )}
        {hover && width > 0 && (
          <Tooltip
            x={hover.px}
            y={hover.py}
            width={width}
            title={labels[hover.i]}
            items={series.filter((s) => s.values.has(xs[hover.i].key)).map((s) => ({ key: s.label, slot: series.length > 1 ? s.slot : undefined, value: formatValue(s.values.get(xs[hover.i].key), vFormat) }))}
          />
        )}
      </div>
    </div>
  )
}

/* ----------------------------------------------------------------- scatter */

function ScatterChart({ chart, rows, formats, height }: ChartProps & { chart: Extract<Chart, { type: 'scatter' }> }) {
  const { ref, width } = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const pts = useMemo(() => {
    const slots = new Map<string, number>()
    return rows
      .map((r, i) => {
        const xv = r[chart.x] instanceof Date ? (r[chart.x] as Date).getTime() : r[chart.x]
        const yv = r[chart.y]
        if (typeof xv !== 'number' || typeof yv !== 'number') return null
        const key = chart.series ? String(r[chart.series] ?? '—') : ''
        if (!slots.has(key)) slots.set(key, Math.min(slots.size + 1, 8))
        return { i, x: xv, y: yv, key, slot: slots.get(key)! }
      })
      .filter((p): p is { i: number; x: number; y: number; key: string; slot: number } => !!p)
  }, [rows, chart])
  const series: Series[] = chart.series ? [...new Map(pts.map((p) => [p.key, p.slot])).entries()].map(([key, slot]) => ({ key, label: key, slot, values: new Map() })) : []
  const top = 10
  const bottom = height - 26
  const y = yAxis(Math.min(...pts.map((p) => p.y)), Math.max(...pts.map((p) => p.y)), top, bottom, formats[chart.y], false)
  const left = y.width
  const right = width - 12
  const time = rows.some((r) => r[chart.x] instanceof Date)
  const xlo = Math.min(...pts.map((p) => p.x))
  const xhi = Math.max(...pts.map((p) => p.x))
  // Whole-number data (counts) gets whole-number ticks.
  const whole = pts.every((p) => Number.isInteger(p.x))
  const xt = time ? timeTicks(xlo, xhi, 6).map((d) => d.getTime()) : niceTicks(xlo, xhi, Math.max(2, Math.floor((right - left) / 80))).filter((t) => !whole || Number.isInteger(t))
  const sx = linear(time ? xlo : xt[0], time ? xhi : xt[xt.length - 1], left + 6, right - 6)
  const h = hover === null ? undefined : pts[hover]

  return (
    <div className="viz-chart">
      <Legend series={series} />
      <div ref={ref} className="viz-plot" style={{ height }}>
        {width > 0 && (
          <svg
            width={width}
            height={height}
            onPointerMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect()
              const px = e.clientX - r.left
              const py = e.clientY - r.top
              let best: number | null = null
              let bd = 20 * 20
              pts.forEach((p, i) => {
                const d = (sx(p.x) - px) ** 2 + (y.scale(p.y) - py) ** 2
                if (d < bd) {
                  bd = d
                  best = i
                }
              })
              setHover(best)
            }}
            onPointerLeave={() => setHover(null)}
          >
            <Grid y={y} left={left} right={right} />
            {pts.map((p, i) => (
              <circle key={p.i} className={`viz-dot${hover === i ? ' on' : ''}`} cx={sx(p.x)} cy={y.scale(p.y)} r={hover === i ? 6 : 4} fill={color(p.slot)} />
            ))}
            <XLabels items={xt.filter((t) => t >= xlo && t <= xhi).map((t) => ({ x: sx(t), label: formatTick(time ? new Date(t) : t, formats[chart.x], xhi - xlo) }))} y={height - 8} />
          </svg>
        )}
        {h && width > 0 && (
          <Tooltip
            x={sx(h.x)}
            y={y.scale(h.y)}
            width={width}
            title={chart.label ? formatValue(rows[h.i][chart.label], formats[chart.label]) : h.key || `Row ${h.i + 1}`}
            items={[
              { key: chart.x, value: formatValue(rows[h.i][chart.x], formats[chart.x]) },
              { key: chart.y, value: formatValue(rows[h.i][chart.y], formats[chart.y]) },
              ...(chart.series && chart.label ? [{ key: chart.series, slot: h.slot, value: h.key }] : []),
            ]}
          />
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ number */

function NumberTile({ chart, rows, formats }: Omit<ChartProps, 'height'> & { chart: Extract<Chart, { type: 'number' }> }) {
  const row = rows[0]
  const v = row[chart.value]
  const prev = chart.compare ? row[chart.compare] : undefined
  let delta: ReactNode = null
  if (typeof v === 'number' && typeof prev === 'number' && prev !== 0) {
    const change = (v - prev) / Math.abs(prev)
    const up = change >= 0
    // The colour says whether the change is good news; the arrow, which way it went.
    const better = chart.good === 'down' ? !up : up
    delta = (
      <span className={`viz-delta ${better ? 'up' : 'down'}`}>
        <span aria-hidden="true">{up ? '▲' : '▼'}</span> {formatValue(Math.abs(change), 'percent')} {up ? 'up' : 'down'} from {formatValue(prev, formats[chart.value])}
      </span>
    )
  }
  return (
    <div className="viz-number">
      <div className="viz-number-value">{formatValue(v, formats[chart.value])}</div>
      {chart.caption && <div className="viz-number-caption">{chart.caption}</div>}
      {delta}
    </div>
  )
}

