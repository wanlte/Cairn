<script setup lang="ts">
import { computed, ref } from 'vue'
import { Activity, ChevronRight } from 'lucide-vue-next'
import type { DriftPoint } from '../types'

const props = defineProps<{ points: DriftPoint[] }>()

const selected = ref<number | null>(null)

const chart = computed(() => {
  const values = props.points.map((point) => point.claims.length)
  const max = Math.max(1, ...values)
  const step = values.length > 1 ? 260 / (values.length - 1) : 0
  const dots = values.map((value, index) => ({
    x: 20 + index * step,
    y: 70 - (value / max) * 52,
    value,
  }))
  return { dots, line: dots.map((dot) => `${dot.x},${dot.y}`).join(' ') }
})

const activePoint = computed(() =>
  props.points.find((point) => point.snapshot_id === selected.value) || null,
)

function shortPeriod(value: string): string {
  return value.length > 10 ? value.slice(-7) : value
}
</script>

<template>
  <section class="card animate-fade-up">
    <div class="card-head">
      <div>
        <h2 class="text-[16px] font-semibold text-ink">想法是怎么一步步变的</h2>
        <p class="mt-1 text-[12px] text-muted">每个点是一次画像，线往上说明记下来的稳定结论变多了。</p>
      </div>
      <span class="badge blue">{{ points.length }} 次画像</span>
    </div>

    <div v-if="!points.length" class="empty">还没有画像快照，生成两次以上就能看出变化。</div>
    <template v-else>
      <svg viewBox="0 0 300 84" class="h-24 w-full" preserveAspectRatio="none">
        <line x1="20" y1="70" x2="280" y2="70" stroke="#e4e8f0" stroke-width="1" />
        <polyline :points="chart.line" fill="none" stroke="#4f46e5" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
        <circle
          v-for="(dot, index) in chart.dots"
          :key="index"
          :cx="dot.x"
          :cy="dot.y"
          :r="selected === points[index].snapshot_id ? 5 : 3.5"
          :fill="selected === points[index].snapshot_id ? '#0f766e' : '#14b8a6'"
          class="cursor-pointer"
          @click="selected = points[index].snapshot_id"
        />
      </svg>
      <div class="flex justify-between text-[11px] text-[#9aa2b4]">
        <span>{{ shortPeriod(points[0].period) }}</span>
        <span>最多 {{ Math.max(...points.map((point) => point.claims.length)) }} 条结论</span>
        <span>{{ shortPeriod(points[points.length - 1].period) }}</span>
      </div>

      <div v-if="activePoint" class="mt-4 rounded-[14px] border border-brand/15 bg-white p-4">
        <div class="flex items-center justify-between gap-2">
          <p class="text-[13px] font-semibold text-ink">{{ activePoint.period }} 的画像</p>
          <span class="text-[11px] text-muted">{{ activePoint.claims.length }} 条结论</span>
        </div>
        <ul class="mt-3 space-y-2">
          <li v-for="claim in activePoint.claims" :key="`${claim.group}-${claim.key}`" class="flex items-start gap-2 text-[12px] leading-relaxed text-[#5b6478]">
            <ChevronRight :size="13" class="mt-0.5 shrink-0 text-brand" />
            <span><b class="font-semibold text-ink">{{ claim.key }}</b>：{{ claim.value }}</span>
          </li>
        </ul>
        <p v-if="!activePoint.claims.length" class="mt-2 text-[12px] text-[#9aa2b4]">这次没有留下结论。</p>
      </div>
      <p v-else class="mt-4 flex items-center gap-1.5 text-[12px] text-muted">
        <Activity :size="13" /> 点一个圆点看那次画像记下了什么。
      </p>
    </template>
  </section>
</template>
