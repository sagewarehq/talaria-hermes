/**
 * Datagen's charts for Talaria canvases: its SVG ChartView, data helpers and chart themes (copied from
 * sagewarehq/studio filetypes/viz/kit), plus a Panel, Grid and Stat that take rows directly instead of a SQL query.
 *
 *   import { Panel, Grid, Chart, useChartTheme } from 'viz'
 *   html`<${Grid}>
 *     <${Panel} title="Revenue" width="half" chart=${{ type: 'area', x: 'month', y: 'revenue' }} rows=${rows} />
 *   </${Grid}>`
 */
import { createElement as h, useEffect, type ReactNode } from 'react'
import { ChartView } from './Charts.tsx'
import { formatsFor } from './data.ts'
import { defineChartTheme, type ChartTheme } from './themes/define.ts'
import berry from './themes/berry.ts'
import candy from './themes/candy.ts'
import classic from './themes/classic.ts'
import datagen from './themes/datagen.ts'
import earth from './themes/earth.ts'
import forest from './themes/forest.ts'
import ink from './themes/ink.ts'
import neon from './themes/neon.ts'
import nordic from './themes/nordic.ts'
import ocean from './themes/ocean.ts'
import pastel from './themes/pastel.ts'
import retro from './themes/retro.ts'
import sunset from './themes/sunset.ts'
import vivid from './themes/vivid.ts'

export { ChartView, formatsFor, defineChartTheme }
export { formatValue, formatTick, niceTicks, timeTicks, linear, buildSeries } from './data.ts'

type Row = Record<string, unknown>

export const THEMES: Record<string, Omit<ChartTheme, 'id'>> = { datagen, berry, candy, classic, earth, forest, ink, neon, nordic, ocean, pastel, retro, sunset, vivid }

/** Set the chart colours for the page: a theme's name (datagen, ocean, neon, …) or one made with defineChartTheme. */
export function setChartTheme(theme: string | Omit<ChartTheme, 'id'>, el: HTMLElement = document.documentElement) {
  const t = typeof theme === 'string' ? (THEMES[theme] ?? datagen) : theme
  t.light.series.forEach((_, i) => el.style.setProperty(`--series-${i + 1}`, `light-dark(${t.light.series[i]}, ${t.dark.series[i]})`))
  el.style.setProperty('--chart-grid', `light-dark(${t.light.grid}, ${t.dark.grid})`)
  el.style.setProperty('--chart-axis', `light-dark(${t.light.axis}, ${t.dark.axis})`)
}

export function useChartTheme(theme: string | Omit<ChartTheme, 'id'>) {
  useEffect(() => setChartTheme(theme), [theme])
}

/** A chart from rows: line, area, bar (stacked, horizontal), scatter, or a headline number. */
export function Chart({ chart, rows, formats, height = 240 }: { chart: any; rows: Row[]; formats?: Record<string, any>; height?: number }) {
  const keys = rows.length ? Object.keys(rows[0]) : []
  return h(ChartView, { chart, rows, height, formats: formatsFor(rows, keys, {}, formats) })
}

/** A card: a title, a line under it, and a chart from `chart` + `rows`, or anything as children. */
export function Panel({ title, description, width = 'full', chart, rows, formats, height, children, className = '' }: {
  title?: ReactNode; description?: ReactNode; width?: 'full' | 'half' | 'third' | 'quarter'; chart?: any; rows?: Row[]
  formats?: Record<string, any>; height?: number; children?: ReactNode; className?: string
}) {
  const number = chart?.type === 'number'
  return h('section', { className: `viz-panel w-${width}${number ? ' is-number' : ''} ${className}` },
    (title || description) && h('header', { className: 'viz-panel-head' },
      h('div', { className: 'viz-panel-titles' }, title && h('h2', null, title), description && h('p', null, description))),
    chart && rows ? h(Chart, { chart, rows, formats, height: height ?? (number ? 0 : 240) }) : null,
    children)
}

/** Panels side by side, as wide as each says, wrapping; on a phone, halves and thirds take the full width. */
export function Grid({ children, className = '' }: { children?: ReactNode; className?: string }) {
  return h('div', { className: `viz-grid ${className}` }, children)
}

/** A headline number in a panel: the value, its change against `compare`, a caption. */
export function Stat({ title, value, compare, caption, good = 'up', format, width = 'half' }: {
  title?: ReactNode; value: number; compare?: number; caption?: string; good?: 'up' | 'down'; format?: any; width?: 'full' | 'half' | 'third' | 'quarter'
}) {
  const rows = [{ value, compare }]
  return h(Panel, { title, width, chart: { type: 'number', value: 'value', compare: compare == null ? undefined : 'compare', caption, good }, rows, formats: format ? { value: format, compare: format } : undefined })
}
