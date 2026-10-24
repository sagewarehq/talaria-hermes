import { defineChartTheme } from './define.ts'

export default defineChartTheme({
  label: 'Earth',
  description: 'Clay, olive and ochre',
  light: { series: ['#8c564b', '#a3a31c', '#6b8e23', '#d2691e', '#556b2f', '#cd853f', '#a0522d', '#7a7a2a'], grid: '#e7e1d6', axis: '#cfc5b4' },
  dark: { series: ['#b07a6f', '#d4d54a', '#8fb64a', '#e88a45', '#7f9a50', '#e0a066', '#c47a55', '#a8a832'], grid: '#2e2a24', axis: '#403a31' },
})
