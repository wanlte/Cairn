<script setup lang="ts">
import { AlertCircle, Activity, Gauge, ShieldCheck } from 'lucide-vue-next'
import type { MetricsOverview } from '../types'
import MetricChart from './MetricChart.vue'

const props = defineProps<{ data: MetricsOverview }>()

function pct(value: number): string {
  return `${Math.round(value * 100)}%`
}
</script>

<template>
  <div class="space-y-5">
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div class="stat-card">
        <div class="flex items-center gap-2 text-muted"><Gauge :size="15" /> 响应 P95</div>
        <p class="mt-2 text-[26px] font-semibold text-ink">{{ data.system.latency_p95_ms }}<span class="text-[13px] text-muted"> ms</span></p>
        <p class="mt-1 text-[11px] text-[#0f766e]">端到端 P50 {{ data.system.latency_p50_ms }} ms</p>
      </div>
      <div class="stat-card">
        <div class="flex items-center gap-2 text-muted"><Activity :size="15" /> 接口成功率</div>
        <p class="mt-2 text-[26px] font-semibold text-ink">{{ pct(data.system.success_rate) }}</p>
        <p class="mt-1 text-[11px] text-muted">{{ data.system.total_requests }} 次调用</p>
      </div>
      <div class="stat-card">
        <div class="flex items-center gap-2 text-muted"><ShieldCheck :size="15" /> 证据命中率</div>
        <p class="mt-2 text-[26px] font-semibold text-ink">{{ pct(data.quality.evidence_hit_rate) }}</p>
        <p class="mt-1 text-[11px] text-muted">画像稳定 {{ pct(data.quality.profile_stability) }}</p>
      </div>
      <div class="stat-card">
        <div class="flex items-center gap-2 text-muted"><AlertCircle :size="15" /> 模型成本</div>
        <p class="mt-2 text-[26px] font-semibold text-ink">¥{{ data.cost.total_cost_cny.toFixed(4) }}</p>
        <p class="mt-1 text-[11px] text-muted">{{ data.cost.total_tokens }} tokens · {{ data.cost.total_calls }} 次</p>
      </div>
    </div>

    <div class="grid gap-5 lg:grid-cols-2">
      <section class="card">
        <h3 class="text-[15px] font-semibold text-ink">延迟趋势</h3>
        <p class="mb-3 mt-1 text-[12px] text-muted">每天平均耗时，单位毫秒。</p>
        <MetricChart
          type="line"
          :categories="data.system.latency_trend.map((p) => p.bucket)"
          :series="[{ name: '平均延迟', data: data.system.latency_trend.map((p) => p.value) }]"
        />
      </section>
      <section class="card">
        <h3 class="text-[15px] font-semibold text-ink">成本趋势</h3>
        <p class="mb-3 mt-1 text-[12px] text-muted">每天模型调用花费，单位元。</p>
        <MetricChart
          type="bar"
          :categories="data.cost.cost_trend.map((p) => p.bucket)"
          :series="[{ name: '成本', data: data.cost.cost_trend.map((p) => p.value) }]"
        />
      </section>
      <section class="card">
        <h3 class="text-[15px] font-semibold text-ink">速度-质量四象限</h3>
        <p class="mb-3 mt-1 text-[12px] text-muted">横轴耗时（秒），纵轴证据命中率。理想位置是左下角。</p>
        <MetricChart
          v-if="data.quality.speed_accuracy.length"
          type="scatter"
          :categories="data.quality.speed_accuracy.map((p) => p.label)"
          :series="[
            { name: '耗时', data: data.quality.speed_accuracy.map((p) => p.fast) },
            { name: '准确率', data: data.quality.speed_accuracy.map((p) => p.accurate) },
          ]"
        />
        <p v-else class="py-12 text-center text-[12px] text-muted">还没有复盘调用，暂无数据。</p>
      </section>
      <section class="card">
        <h3 class="text-[15px] font-semibold text-ink">质量拆解</h3>
        <p class="mb-3 mt-1 text-[12px] text-muted">格式、依据、申诉与画像稳定性的当前口径。</p>
        <div class="grid grid-cols-2 gap-3">
          <div class="rounded-[12px] bg-[#f8fafc] p-3">
            <p class="text-[11px] text-muted">格式通过率</p>
            <p class="mt-1 text-[18px] font-semibold text-ink">{{ pct(data.quality.schema_pass_rate) }}</p>
          </div>
          <div class="rounded-[12px] bg-[#f8fafc] p-3">
            <p class="text-[11px] text-muted">申诉改判率</p>
            <p class="mt-1 text-[18px] font-semibold text-ink">{{ pct(data.quality.appeal_correction_rate) }}</p>
          </div>
          <div class="rounded-[12px] bg-[#f8fafc] p-3">
            <p class="text-[11px] text-muted">重试率</p>
            <p class="mt-1 text-[18px] font-semibold text-ink">{{ pct(data.cost.retry_rate) }}</p>
          </div>
          <div class="rounded-[12px] bg-[#f8fafc] p-3">
            <p class="text-[11px] text-muted">任务完成率</p>
            <p class="mt-1 text-[18px] font-semibold text-ink">{{ pct(data.system.task_completion_rate) }}</p>
          </div>
        </div>
      </section>
    </div>

    <section class="card">
      <h3 class="text-[15px] font-semibold text-ink">功能渗透</h3>
      <p class="mb-3 mt-1 text-[12px] text-muted">各功能被使用的次数。</p>
      <MetricChart
        type="bar"
        :categories="data.behavior.feature_penetration.map((f) => f.feature)"
        :series="[{ name: '使用次数', data: data.behavior.feature_penetration.map((f) => f.count) }]"
      />
    </section>
  </div>
</template>

<style scoped>
.stat-card {
  border-radius: 14px;
  border: 1px solid #eef0f6;
  background: #fff;
  padding: 16px;
}
</style>
