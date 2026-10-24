import { defineChartTheme } from './define.ts'

export default defineChartTheme({
  label: 'Neon',
  description: 'Electric, best on dark',
  light: { series: ['#0096d6', '#e0218a', '#00a86b', '#e0a000', '#8a3ffc', '#f04e23', '#00a3a8', '#9aa800'] },
  dark: { series: ['#38c6ff', '#ff5ec8', '#2ef0a8', '#ffc933', '#b47bff', '#ff7a5c', '#2ee0e5', '#e2ef2a'] },
})
