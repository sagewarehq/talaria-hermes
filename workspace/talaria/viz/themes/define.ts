/**
 * A chart theme: the colors a vault's visualizations draw with, in light mode and in dark. One file per theme in this
 * folder, named for its id (`ocean.ts` → "ocean", what a vault's studio.json says), default-exporting
 * `defineChartTheme({ … })`. Dropping a file here adds the theme to Settings › Appearance; nothing else names them.
 *
 *   export default defineChartTheme({
 *     label: 'Ocean',
 *     description: 'Cool blues and greens',
 *     light: { series: ['#0b5394', …eight in all], grid: '#e0e6ea', axis: '#c2cdd6' },
 *     dark: { series: ['#4d8fd1', …], grid: '#26303a', axis: '#34414d' },
 *   })
 *
 * Series colors are drawn in slot order (the first is a single series'), so put the most distinct ones first, and
 * keep adjacent ones apart in hue and lightness. Each mode's colors must read on its page: no pale yellows on white.
 */

/** Exactly eight: a chart draws up to eight series and folds the rest into "Other". */
export type Series = [string, string, string, string, string, string, string, string]

export interface ChartPalette {
  series: Series
  /** The grid lines behind the marks; default a quiet neutral. */
  grid?: string
  /** The axis lines; default a little stronger than the grid. */
  axis?: string
}

export interface ChartThemeInput {
  label: string
  /** A few words on its look, under its name in Settings. */
  description: string
  light: ChartPalette
  dark: ChartPalette
}

export interface ChartTheme {
  /** Its file's name. */
  id: string
  label: string
  description: string
  light: Required<ChartPalette>
  dark: Required<ChartPalette>
}

const DEFAULTS = { light: { grid: '#e1e0d9', axis: '#c3c2b7' }, dark: { grid: '#2c2c2a', axis: '#383835' } }

/** A theme, as its file declares it (its id comes from the file's name: see ./index.ts). */
export const defineChartTheme = (t: ChartThemeInput): Omit<ChartTheme, 'id'> => ({
  label: t.label,
  description: t.description,
  light: { ...DEFAULTS.light, ...t.light },
  dark: { ...DEFAULTS.dark, ...t.dark },
})
