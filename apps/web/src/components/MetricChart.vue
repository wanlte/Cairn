<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
])

const props = withDefaults(
  defineProps<{
    type: 'line' | 'bar' | 'pie' | 'scatter'
    categories?: string[]
    series: { name: string; data: number[] }[]
    height?: number
    suffix?: string
  }>(),
  { height: 220, suffix: '', categories: () => [] },
)

const option = computed(() => {
  if (props.type === 'pie') {
    return {
      tooltip: { trigger: 'item' },
      series: [
        {
          name: props.series[0]?.name || '占比',
          type: 'pie',
          radius: ['45%', '70%'],
          data: props.categories.map((name, index) => ({
            name,
            value: props.series[0]?.data[index] || 0,
          })),
        },
      ],
    }
  }

  if (props.type === 'scatter') {
    const x = props.series[0]?.data || []
    const y = props.series[1]?.data || []
    return {
      tooltip: { trigger: 'item' },
      grid: { left: 50, right: 20, top: 20, bottom: 40 },
      xAxis: { name: '秒', type: 'value' },
      yAxis: { name: '准确率', type: 'value', min: 0, max: 1 },
      series: [
        {
          name: '速度-质量',
          type: 'scatter',
          symbolSize: 14,
          data: props.categories.map((name, index) => ({
            name,
            value: [x[index] || 0, y[index] || 0],
          })),
        },
      ],
    }
  }

  return {
    tooltip: { trigger: 'axis' },
    legend: { data: props.series.map((s) => s.name), bottom: 0 },
    grid: { left: 50, right: 20, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: props.categories },
    yAxis: { type: 'value' },
    series: props.series.map((s) => ({
      name: s.name,
      type: props.type,
      smooth: props.type === 'line',
      data: s.data,
    })),
  }
})
</script>

<template>
  <div :style="{ height: `${height}px` }">
    <VChart :option="option" autoresize />
  </div>
</template>
