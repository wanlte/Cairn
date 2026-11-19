<script setup lang="ts">
import { computed } from 'vue'
import { Activity, AlertTriangle, CheckCircle2, LoaderCircle } from 'lucide-vue-next'
import type { Coverage } from '../types'

const props = defineProps<{ coverage: Coverage | null; loading?: boolean }>()

const tone = computed(() => {
  if (!props.coverage) return 'gray'
  if (props.coverage.level === '较高') return 'green'
  if (props.coverage.level === '中等') return 'amber'
  return 'red'
})

const metrics = computed(() => {
  const item = props.coverage
  if (!item) return []
  return [
    { label: '时间跨度', value: `${item.span_days} 天` },
    { label: '场景类型', value: `${item.scenarios} 类` },
    { label: '情绪密度', value: `${Math.round(item.emotion_density * 100)}%` },
    { label: '记录来源', value: `${item.sources} 个` },
    { label: '反事实补录', value: `${item.counterfactuals} 条` },
  ]
})
</script>

<template>
  <section class="card animate-fade-up">
    <div class="card-head">
      <div class="flex items-center gap-2">
        <Activity :size="18" class="text-brand" />
        <h2 class="text-[16px] font-semibold text-ink">样本体检</h2>
      </div>
      <span v-if="coverage" class="badge" :class="tone">{{ coverage.level }}</span>
    </div>

    <div v-if="loading" class="flex items-center gap-2 py-8 text-[13px] text-muted">
      <LoaderCircle :size="16" class="animate-spin text-brand" /> 正在检查样本覆盖情况…
    </div>

    <template v-else-if="coverage">
      <div class="flex items-center gap-5 rounded-[16px] bg-gradient-to-r from-[#eef0ff] to-[#eafaf7] p-5">
        <div class="text-[46px] font-semibold leading-none text-ink">{{ coverage.score }}</div>
        <div class="flex-1">
          <div class="h-2 overflow-hidden rounded-full bg-white/75">
            <div
              class="h-full rounded-full bg-gradient-to-r from-brand to-brand-teal transition-all duration-700"
              :style="{ width: `${coverage.score}%` }"
            />
          </div>
          <p class="mt-2 text-[13px] leading-relaxed text-[#5b6478]">{{ coverage.summary }}</p>
        </div>
      </div>

      <div class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-5">
        <div
          v-for="metric in metrics"
          :key="metric.label"
          class="rounded-[12px] border border-[#eef0f5] bg-white/70 p-3 text-center"
        >
          <div class="text-[16px] font-semibold text-ink">{{ metric.value }}</div>
          <div class="mt-1 text-[11px] text-muted">{{ metric.label }}</div>
        </div>
      </div>

      <div v-if="coverage.reasons.length" class="tip mt-5">
        <div class="flex items-start gap-2">
          <AlertTriangle :size="15" class="mt-0.5 shrink-0 text-[#b45309]" />
          <div>
            <p class="font-semibold">这些地方还能补一补</p>
            <ul class="mt-1 space-y-1">
              <li v-for="reason in coverage.reasons" :key="reason" class="text-[12px] text-[#5b6478]">
                · {{ reason }}
              </li>
            </ul>
          </div>
        </div>
      </div>
      <div v-else class="mt-5 flex items-center gap-2 text-[13px] text-[#0f766e]">
        <CheckCircle2 :size="15" /> 样本覆盖比较均衡，可以继续往下分析。
      </div>
    </template>

    <div v-else class="empty">还没有样本体检数据，先记几段对话再来看看。</div>
  </section>
</template>
