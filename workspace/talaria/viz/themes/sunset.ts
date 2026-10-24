import { defineChartTheme } from './define.ts'

export default defineChartTheme({
  label: 'Sunset',
  description: 'Warm reds, oranges and golds',
  light: { series: ['#d1495b', '#ef8a3a', '#e9b949', '#8c2f39', '#f2a07b', '#b5651d', '#6d597a', '#c9a227'], grid: '#ebe2d9', axis: '#d6c8ba' },
  dark: { series: ['#e8677a', '#f5a160', '#f0cb6c', '#c45563', '#f6b898', '#d6863f', '#9d87ab', '#ddb94a'], grid: '#302822', axis: '#423830' },
})
