import { defineChartTheme } from './define.ts'

export default defineChartTheme({
  label: 'Forest',
  description: 'Greens through moss to bark',
  light: { series: ['#1b4332', '#2d6a4f', '#40916c', '#52b788', '#74c69d', '#95d5b2', '#8a6c3a', '#b08d57'], grid: '#dfe7e1', axis: '#c3d0c6' },
  dark: { series: ['#95d5b2', '#74c69d', '#52b788', '#40916c', '#b7e4c7', '#2d8a63', '#c9a46c', '#a68148'], grid: '#25302a', axis: '#36443b' },
})
