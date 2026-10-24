import { defineChartTheme } from './define.ts'

export default defineChartTheme({
  label: 'Ocean',
  description: 'Cool blues and greens',
  light: { series: ['#0b5394', '#2a9d8f', '#48a9d6', '#264653', '#7fb7be', '#43aa8b', '#577590', '#90be6d'], grid: '#e0e6ea', axis: '#c2cdd6' },
  dark: { series: ['#4d8fd1', '#3cbfae', '#6cc4ea', '#7d9cab', '#9fd0d6', '#5ccaa6', '#8aa3c0', '#a9d488'], grid: '#26303a', axis: '#34414d' },
})
