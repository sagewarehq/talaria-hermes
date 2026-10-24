import { defineChartTheme } from './define.ts'

export default defineChartTheme({
  label: 'Berry',
  description: 'Plums, raspberries and wine',
  light: { series: ['#7b2cbf', '#c9184a', '#ff4d6d', '#9d4edd', '#590d22', '#c77dff', '#a4133c', '#5a189a'] },
  dark: { series: ['#b388eb', '#ff4d6d', '#ff8fa3', '#c77dff', '#e0607e', '#e0aaff', '#ff758f', '#9d6bd8'] },
})
