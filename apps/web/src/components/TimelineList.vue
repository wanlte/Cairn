<script setup lang="ts">
import type { TimelineEvent } from '../types'

const props = defineProps<{ events: TimelineEvent[]; lowPrecisionCount?: number }>()

const TYPE_LABELS: Record<string, string> = {
  conversation: '记录导入',
  turn: '对话',
  fragment: '观察',
  counterfactual: '补录',
  review: '复盘',
  profile: '画像',
  action: '行动项',
}

const TYPE_TONES: Record<string, string> = {
  conversation: 'blue',
  turn: 'gray',
  fragment: 'gray',
  counterfactual: 'green',
  review: 'blue',
  profile: 'amber',
  action: 'green',
}

function timeOf(value: string | null): string {
  if (!value) return '时间不确定'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间不确定'
  return date.toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function precisionOf(item: TimelineEvent): string {
  if (item.low_confidence) return '时间不准确'
  if (item.time_precision === 'HIGH') return ''
  return '时间估算'
}
</script>

<template>
  <section class="card animate-fade-up">
    <div class="card-head">
      <div>
        <h2 class="text-[16px] font-semibold text-ink">这些记录的时间线</h2>
        <p class="mt-1 text-[12px] text-muted">
          不同来源的记录按时间排在一起，标着「时间估算」的表示当时没记下准确时间。
        </p>
      </div>
      <span class="badge gray">{{ props.events.length }} 条</span>
    </div>

    <div v-if="!props.events.length" class="empty">还没有可排时间序列的记录。</div>
    <div v-else class="relative pl-6">
      <div class="absolute bottom-2 left-[7px] top-2 w-px bg-[#e4e8f0]" />
      <div v-for="item in props.events" :key="item.id" class="relative pb-5 last:pb-0">
        <span
          class="absolute -left-[22px] top-2 h-[11px] w-[11px] rounded-full border-2 border-white bg-brand shadow-sm"
        />
        <div class="rounded-[14px] border border-[#eef0f5] bg-white/75 p-3.5 transition-all hover:border-brand/25 hover:shadow-soft">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-[12px] font-medium text-muted">{{ timeOf(item.occurred_at) }}</span>
            <span class="badge" :class="TYPE_TONES[item.event_type] || 'gray'">
              {{ TYPE_LABELS[item.event_type] || item.event_type }}
            </span>
            <span v-if="precisionOf(item)" class="badge amber">{{ precisionOf(item) }}</span>
          </div>
          <p class="mt-2 text-[14px] font-semibold text-ink">{{ item.title }}</p>
          <p v-if="item.summary" class="mt-1 line-clamp-2 text-[12px] leading-relaxed text-muted">
            {{ item.summary }}
          </p>
        </div>
      </div>
    </div>

    <p v-if="props.lowPrecisionCount" class="tip mt-4">
      有 {{ props.lowPrecisionCount }} 条记录的时间是推断出来的，别把它们当成精确发生顺序。
    </p>
  </section>
</template>
