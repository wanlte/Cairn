<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Check,
  ChevronRight,
  ExternalLink,
  Lightbulb,
  ListChecks,
  LoaderCircle,
  RefreshCcw,
  Sparkles,
} from 'lucide-vue-next'
import { reviewApi } from '../api/client'
import type { AgentResult, ReviewReport } from '../types'
import { friendlyVerdict, verdictTone } from '../utils/friendly'
import {
  comparisonText,
  distributionBars,
  overviewOf,
  reportStats,
  sectionItems,
  text,
} from '../utils/review'

const props = defineProps<{ result: AgentResult }>()
const emit = defineEmits<{ (event: 'next'): void }>()
const router = useRouter()

const report = ref<ReviewReport | null>(null)
const loading = ref(false)
const failed = ref(false)

const hasReportId = computed(() => props.result.report_id != null)
const hasRichReport = computed(() => {
  const value = report.value
  if (!value) return false
  return Boolean(
    value.items.length ||
    value.action_items.length ||
    Number(overviewOf(value).dialogue_count) > 0 ||
    comparisonText(value),
  )
})
const stats = computed(() => reportStats(report.value))
const comparison = computed(() => comparisonText(report.value))
const domainBars = computed(() =>
  distributionBars(overviewOf(report.value).domain_distribution, 'domain', 3),
)
const topicBars = computed(() =>
  distributionBars(overviewOf(report.value).investment_distribution, 'topic', 3),
)
const firstEvent = computed(() => sectionItems(report.value, 'key_event')[0] || null)
const firstJudgment = computed(() => sectionItems(report.value, 'judgment')[0] || null)
const firstChange = computed(() => sectionItems(report.value, 'cognitive_change')[0] || null)
const firstAction = computed(() => report.value?.action_items?.[0] || null)
const hasBars = computed(() => domainBars.value.length > 0 || topicBars.value.length > 0)

async function loadReport(): Promise<void> {
  const id = props.result.report_id
  report.value = null
  failed.value = false
  if (id == null) return
  loading.value = true
  try {
    report.value = await reviewApi.get(id)
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

watch(() => props.result.report_id, loadReport, { immediate: true })

function openReport(): void {
  if (props.result.report_id == null) return
  router.push({ name: 'report-detail', params: { id: props.result.report_id } })
}

function handleNext(): void {
  if (props.result.kind === '复盘' && props.result.next_label === '更新画像') {
    router.push({ name: 'profile', query: { generate: '1' } })
    return
  }
  emit('next')
}
</script>

<template>
  <div class="animate-fade-up overflow-hidden rounded-[20px] border border-white/80 bg-white/90 shadow-soft">
    <div class="h-1 bg-gradient-to-r from-brand via-brand-light to-brand-teal"></div>
    <div class="p-5 sm:p-6">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <span class="rounded-full bg-brand/10 px-3 py-1 text-[11px] font-semibold text-brand">{{ result.kind }}</span>
        <h3 class="text-[18px] font-semibold text-ink">{{ result.title }}</h3>
      </div>

      <div v-if="hasReportId && loading" class="flex items-center gap-2 rounded-[14px] bg-[#f8fafc] px-4 py-6 text-[13px] text-[#7a839a]">
        <LoaderCircle :size="15" class="animate-spin text-brand" /> 正在把复盘整理成看得见的内容…
      </div>

      <div v-else-if="hasReportId && report && hasRichReport" class="space-y-4">
        <p class="whitespace-pre-wrap rounded-[14px] bg-brand/5 px-4 py-3 text-[13px] leading-[1.85] text-[#434c60]">
          {{ result.summary }}
        </p>

        <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <div class="rounded-[14px] bg-[#f8fafc] px-3 py-3">
            <p class="text-[20px] font-semibold text-brand">{{ stats.dialogueCount }}</p>
            <p class="mt-0.5 text-[11px] text-[#8b93a7]">回看的对话</p>
          </div>
          <div class="rounded-[14px] bg-[#f8fafc] px-3 py-3">
            <p class="text-[20px] font-semibold text-brand">{{ stats.keyEvents }}</p>
            <p class="mt-0.5 text-[11px] text-[#8b93a7]">值得回看的事</p>
          </div>
          <div class="rounded-[14px] bg-[#f8fafc] px-3 py-3">
            <p class="text-[20px] font-semibold text-brand">{{ stats.judgments }}</p>
            <p class="mt-0.5 text-[11px] text-[#8b93a7]">判断复盘</p>
          </div>
          <div class="rounded-[14px] bg-[#f8fafc] px-3 py-3">
            <p class="text-[20px] font-semibold text-brand">{{ stats.actions }}</p>
            <p class="mt-0.5 text-[11px] text-[#8b93a7]">接下来要做</p>
          </div>
        </div>

        <p v-if="comparison" class="flex items-start gap-2 text-[13px] leading-relaxed text-[#5b6478]">
          <Sparkles :size="14" class="mt-0.5 shrink-0 text-brand" /> {{ comparison }}
        </p>

        <div v-if="hasBars" class="rounded-[14px] border border-[#eef0f6] px-4 py-3.5">
          <p class="mb-3 text-[12px] font-semibold text-[#5b6478]">精力花在了哪里</p>
          <div class="space-y-2.5">
            <div v-for="(bar, index) in [...domainBars, ...topicBars]" :key="`${bar.label}-${index}`" class="flex items-center gap-2.5">
              <span class="w-24 shrink-0 truncate text-[12px] text-[#5b6478]">{{ bar.label }}</span>
              <div class="progress flex-1"><div :style="{ width: `${bar.percent}%` }"></div></div>
              <span class="w-9 shrink-0 text-right text-[11px] text-[#9aa2b4]">{{ bar.count }} 次</span>
            </div>
          </div>
        </div>

        <div v-if="firstEvent" class="rounded-[14px] border border-[#eef0f6] p-4">
          <div class="mb-2 flex flex-wrap items-center gap-2">
            <p class="text-[12px] font-semibold text-[#5b6478]">最值得回看的一件事</p>
            <span v-if="firstJudgment" class="rounded-full px-2 py-0.5 text-[10px] font-semibold" :class="verdictTone(firstJudgment.verdict)">
              {{ friendlyVerdict(firstJudgment.verdict) }}
            </span>
          </div>
          <p class="text-[14px] font-medium leading-relaxed text-ink">{{ text(firstEvent.payload, 'background') }}</p>
          <p v-if="text(firstEvent.payload, 'my_judgment')" class="mt-2 text-[12px] leading-relaxed text-[#5b6478]">
            当时的判断：{{ text(firstEvent.payload, 'my_judgment') }}
          </p>
          <p v-if="text(firstEvent.payload, 'actual_outcome')" class="mt-1 text-[12px] leading-relaxed text-[#5b6478]">
            后来怎么样：{{ text(firstEvent.payload, 'actual_outcome') }}
          </p>
        </div>

        <div v-if="firstChange" class="flex items-start gap-2.5 rounded-[14px] bg-[#f0fbf8] px-4 py-3.5">
          <Lightbulb :size="15" class="mt-0.5 shrink-0 text-[#0f766e]" />
          <div class="min-w-0 text-[13px] leading-relaxed text-[#434c60]">
            <span class="text-[#8b93a7]">想法变了：</span>
            从「{{ text(firstChange.payload, 'old_belief') }}」到现在更倾向「{{ text(firstChange.payload, 'new_belief') }}」
          </div>
        </div>

        <div v-if="firstAction" class="flex items-start gap-2.5 rounded-[14px] bg-[#f8fafc] px-4 py-3.5">
          <ListChecks :size="15" class="mt-0.5 shrink-0 text-brand" />
          <div class="min-w-0 text-[13px] leading-relaxed text-[#434c60]">
            <p>下一步：{{ firstAction.content }}</p>
            <p v-if="firstAction.verification" class="mt-0.5 text-[12px] text-[#8b93a7]">怎么算做到：{{ firstAction.verification }}</p>
          </div>
        </div>

        <p v-if="report.status !== 'DONE'" class="rounded-[12px] bg-[#fff5e6] px-3 py-2.5 text-[12px] text-[#b45309]">
          这次的内容没能全部写好，完整报告里能看到已经记录下来的部分。
        </p>
      </div>

      <template v-else>
        <p v-if="failed" class="mb-3 rounded-[12px] bg-[#fff5e6] px-3 py-2.5 text-[12px] text-[#b45309]">
          完整报告暂时打不开，先看看这里的速览。
        </p>
        <p v-else-if="hasReportId && report" class="mb-3 rounded-[12px] bg-[#fff5e6] px-3 py-2.5 text-[12px] text-[#b45309]">
          这次复盘没能完整生成，记录里暂时只有空框架，换个模型再试一次会更完整。
        </p>
        <p class="whitespace-pre-wrap text-[14px] leading-[1.9] text-[#434c60]">{{ result.summary }}</p>
        <div v-if="result.suggestions.length" class="mt-5">
          <p class="mb-2.5 flex items-center gap-1.5 text-[12px] font-semibold text-[#5b6478]">
            <Check :size="14" class="text-[#0f766e]" /> 接下来可以试试
          </p>
          <ul class="space-y-2">
            <li
              v-for="(item, index) in result.suggestions"
              :key="index"
              class="flex items-start gap-2.5 rounded-[12px] bg-[#f8fafc] px-3.5 py-2.5 text-[13px] leading-relaxed text-[#5b6478]"
            >
              <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gradient-to-br from-brand to-brand-teal"></span>
              <span>{{ item }}</span>
            </li>
          </ul>
        </div>
      </template>

      <div class="mt-5 flex flex-wrap items-center gap-2">
        <button
          v-if="hasReportId"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-full bg-brand px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-brand-light"
          @click="openReport"
        >
          查看完整报告 <ExternalLink :size="14" />
        </button>
        <button
          v-if="failed"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-full bg-brand/5 px-4 py-2 text-[13px] font-semibold text-brand transition-colors hover:bg-brand/10"
          @click="loadReport"
        >
          <RefreshCcw :size="13" /> 再试一次
        </button>
        <button
          v-if="result.next_label"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-full bg-brand/5 px-4 py-2 text-[13px] font-semibold text-brand transition-colors hover:bg-brand/10"
          @click="handleNext"
        >
          {{ result.next_label }} <ArrowRight :size="14" />
        </button>
        <span v-if="hasReportId && hasRichReport" class="ml-auto hidden items-center gap-1 text-[11px] text-[#9aa2b4] sm:inline-flex">
          报告里还有判断复盘、想法变化和行动跟踪 <ChevronRight :size="12" />
        </span>
      </div>
    </div>
  </div>
</template>
