import { defineChartTheme } from './define.ts'

export default defineChartTheme({
  label: 'Classic',
  description: 'Familiar, muted analytics colours',
  light: { series: ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948', '#b07aa1', '#9c755f'] },
  dark: { series: ['#6b95c4', '#f5a04a', '#ec7375', '#8fcac5', '#74bd6a', '#f2d466', '#c597b7', '#b8917b'] },
})
