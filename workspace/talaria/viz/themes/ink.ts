import { defineChartTheme } from './define.ts'

export default defineChartTheme({
  label: 'Ink',
  description: 'One hue in steps, for print',
  light: { series: ['#1f3a5f', '#3d6a99', '#6b97c4', '#a3c1de', '#2f4858', '#5c7c8a', '#8aa6b3', '#bcd0d8'], grid: '#e3e5e8', axis: '#c6cad0' },
  dark: { series: ['#d6e4f2', '#a3c1de', '#6b97c4', '#3d6a99', '#c9d8de', '#8aa6b3', '#5c7c8a', '#3b5866'], grid: '#2a2d31', axis: '#3a3f45' },
})
