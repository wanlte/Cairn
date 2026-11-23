<script setup lang="ts">
import { BookOpen, Download, GitBranch, TrendingUp, Users } from 'lucide-vue-next'
import type { MetricsOverview } from '../types'
import MetricChart from './MetricChart.vue'

const props = defineProps<{ data: MetricsOverview }>()

const highlights = [
  { label: '样本覆盖度提升', value: `${props.data.value.coverage_improvement >= 0 ? '+' : ''}${props.data.value.coverage_improvement}`, icon: TrendingUp, hint: '最近报告的覆盖度变化' },
  { label: '连续周回填', value: `${props.data.value.weekly_streak} 周`, icon: BookOpen, hint: '行动闭环持续了多久' },
  { label: '导出次数', value: `${props.data.value.export_count}`, icon: Download, hint: '把结论带走的次数' },
  { label: '关系分析', value: `${props.data.value.pair_analysis_count}`, icon: Users, hint: '双方授权后完成的错位分析' },
]
</script>

<template>
  <div class="space-y-5">
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div v-for="item in highlights" :key="item.label" class="card">
        <div class="flex items-center gap-2 text-muted">
          <component :is="item.icon" :size="15" />
          <span class="text-[12px]">{{ item.label }}</span>
        </div>
        <p class="mt-2 text-[26px] font-semibold text-ink">{{ item.value }}</p>
        <p class="mt-1 text-[11px] text-muted">{{ item.hint }}</p>
      </div>
    </div>

    <section class="card">
      <div class="flex items-center gap-2">
        <GitBranch :size="17" class="text-brand" />
        <h2 class="text-[16px] font-semibold text-ink">从记录到行动的旅程</h2>
      </div>
      <p class="mt-1 text-[12px] text-muted">每一层都是上一层的基础上长出来的。</p>
      <MetricChart
        class="mt-4"
        type="bar"
        :categories="data.behavior.funnel.map((f) => f.label)"
        :series="[{ name: '人数', data: data.behavior.funnel.map((f) => f.count) }]"
      />
    </section>

    <div class="grid gap-5 md:grid-cols-2">
      <section class="card">
        <h3 class="text-[15px] font-semibold text-ink">样本覆盖度分布</h3>
        <p class="mb-3 mt-1 text-[12px] text-muted">覆盖度越高，结论越不偏。</p>
        <MetricChart
          v-if="data.quality.coverage_distribution.length"
          type="pie"
          :categories="data.quality.coverage_distribution.map((d) => d.level)"
          :series="[{ name: '报告数', data: data.quality.coverage_distribution.map((d) => d.count) }]"
        />
        <p v-else class="py-12 text-center text-[12px] text-muted">还没有样本体检数据。</p>
      </section>
      <section class="card">
        <h3 class="text-[15px] font-semibold text-ink">可信度快照</h3>
        <p class="mb-3 mt-1 text-[12px] text-muted">对外展示时，我们优先呈现可追溯的结论。</p>
        <div class="space-y-3">
          <div class="rounded-[12px] bg-[#f4faf8] p-4">
            <p class="text-[12px] text-[#0f766e]">结论有据可查</p>
            <p class="mt-1 text-[22px] font-semibold text-ink">{{ Math.round(data.quality.evidence_hit_rate * 100) }}%</p>
          </div>
          <div class="rounded-[12px] bg-[#eef0ff] p-4">
            <p class="text-[12px] text-brand">画像跨版本稳定</p>
            <p class="mt-1 text-[22px] font-semibold text-ink">{{ Math.round(data.quality.profile_stability * 100) }}%</p>
          </div>
          <div class="rounded-[12px] bg-[#f8fafc] p-4">
            <p class="text-[12px] text-muted">授权与审计事件</p>
            <p class="mt-1 text-[22px] font-semibold text-ink">{{ data.security.audit_events }}</p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
