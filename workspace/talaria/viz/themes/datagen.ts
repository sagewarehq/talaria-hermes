import { defineChartTheme } from './define.ts'

export default defineChartTheme({
  label: 'Datagen',
  description: 'Balanced and colour-blind safe',
  light: { series: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'] },
  dark: { series: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'] },
})
