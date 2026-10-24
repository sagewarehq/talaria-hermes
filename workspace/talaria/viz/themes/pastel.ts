import { defineChartTheme } from './define.ts'

export default defineChartTheme({
  label: 'Pastel',
  description: 'Soft and light, for calm dashboards',
  light: { series: ['#7eb0d5', '#fd7f6f', '#9fcf4a', '#bd7ebe', '#ffb55a', '#e3c935', '#a9a3d1', '#6cc4b6'] },
  dark: { series: ['#8fbde0', '#fe9184', '#c0e87a', '#c992ca', '#ffc070', '#fff180', '#cbc7e5', '#9edcd1'] },
})
