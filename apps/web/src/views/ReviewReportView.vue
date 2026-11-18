<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BookOpen,
  Check,
  CheckCircle2,
  Download,
  FileText,
  Lightbulb,
  ListChecks,
  LoaderCircle,
  RotateCcw,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-vue-next'
import { reviewApi } from '../api/client'
import type { ActionItemRecord, ReviewItem, ReviewReport } from '../types'
import {
  actionStatusTone,
  friendlyActionStatus,
  friendlyAttribution,
  friendlyDate,
  friendlyError,
  friendlyReportStatus,
  friendlyVerdict,
  verdictTone,
} from '../utils/friendly'
import {
  comparisonText,
  distributionBars,
  overviewOf,
  reportStats,
  sectionItems,
  text,
  trendSeries,
} from '../utils/review'

const route = useRoute()
const router = useRouter()

const reports = ref<ReviewReport[]>([])
const current = ref<ReviewReport | null>(null)
const loading = ref(false)
const error = ref('')
const busyId = ref<number | null>(null)
const noteDrafts = ref<Record<number, string>>({})

const reportId = computed(() => {
  const raw = route.params.id
  const id = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isFinite(id) && id > 0 ? id : null
})

const stats = computed(() => reportStats(current.value))
const overview = computed(() => overviewOf(current.value))
const comparison = computed(() => comparisonText(current.value))
const keyEvents = computed(() => sectionItems(current.value, 'key_event'))
const judgments = computed(() => sectionItems(current.value, 'judgment'))
const changes = computed(() => sectionItems(current.value, 'cognitive_change'))
const actions = computed(() => current.value?.action_items || [])
const domainBars = computed(() => distributionBars(overview.value.domain_distribution, 'domain'))
const topicBars = computed(() => distributionBars(overview.value.investment_distribution, 'topic'))
const trend = computed(() => trendSeries(reports.value))
const trendChart = computed(() => {
  const points = trend.value
  const max = Math.max(1, ...points.map((item) => item.value))
  const step = points.length > 1 ? 260 / (points.length - 1) : 0
  const dots = points.map((item, index) => ({
    ...item,
    x: 20 + index * step,
    y: 70 - (item.value / max) * 52,
  }))
  return { max, dots, line: dots.map((dot) => `${dot.x},${dot.y}`).join(' ') }
})
const actionProgress = computed(() =>
  stats.value.actions ? Math.round((stats.value.verified / stats.value.actions) * 100) : 0,
)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    reports.value = await reviewApi.list()
    current.value = reportId.value ? await reviewApi.get(reportId.value) : null
  } catch (err) {
    error.value = friendlyError(err)
    current.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(reportId, () => {
  window.scrollTo({ top: 0, behavior: 'smooth' })
  void load()
})

function openReport(id: number): void {
  router.push({ name: 'report-detail', params: { id } })
}

function goBack(): void {
  router.push({ name: 'reports' })
}

async function updateAction(item: ActionItemRecord, kind: 'verify' | 'reopen'): Promise<void> {
  if (busyId.value !== null) return
  busyId.value = item.id
  error.value = ''
  try {
    const note = noteDrafts.value[item.id]?.trim() || undefined
    const updated =
      kind === 'verify'
        ? await reviewApi.verifyAction(item.id, note)
        : await reviewApi.reopenAction(item.id, note)
    Object.assign(item, updated)
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busyId.value = null
  }
}

async function giveFeedback(item: ReviewItem, decision: 'AGREE' | 'DISAGREE'): Promise<void> {
  if (busyId.value !== null) return
  busyId.value = item.id
  error.value = ''
  try {
    const updated = await reviewApi.feedback(item.id, decision)
    item.feedback = updated.feedback
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busyId.value = null
  }
}

async function exportReport(): Promise<void> {
  if (!current.value) return
  try {
    const markdown = await reviewApi.exportText(current.value.id)
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `我的复盘记录-${current.value.created_at.slice(0, 10)}.md`
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (err) {
    error.value = friendlyError(err)
  }
}
</script>

<template>
  <div class="report-view relative min-h-full">
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="absolute -left-20 top-8 h-72 w-72 rounded-full bg-brand/10 blur-3xl animate-float"></div>
      <div class="absolute -right-20 top-56 h-72 w-72 rounded-full bg-brand-teal/10 blur-3xl animate-float" style="animation-delay: -3s"></div>
    </div>

    <div class="relative mx-auto w-full max-w-[960px] px-5 pb-24 pt-12">
      <div class="mb-7 flex flex-wrap items-end justify-between gap-4 animate-fade-up">
        <div>
          <div class="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-brand to-brand-teal text-white shadow-glow">
            <BookOpen :size="22" />
          </div>
          <h1 class="text-[30px] font-semibold tracking-tight text-ink">
            {{ reportId ? '我的复盘记录' : '复盘记录' }}
          </h1>
          <p class="mt-2 text-[14px] text-[#7a839a]">
            {{ reportId && current
              ? `记于 ${friendlyDate(current.created_at)} · 把这一段看清楚，也把下一步定下来`
              : `一共 ${reports.length} 份记录，随时回来翻一翻` }}
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button v-if="reportId" type="button" class="btn ghost small" @click="goBack">
            <ArrowLeft :size="14" class="mr-1 inline" /> 全部记录
          </button>
          <button v-if="reportId && current" type="button" class="btn ghost small" @click="exportReport">
            <Download :size="14" class="mr-1 inline" /> 导出这份记录
          </button>
        </div>
      </div>

      <p v-if="error" class="mb-5 rounded-[14px] border border-red-100 bg-red-50 px-4 py-3 text-[13px] text-[#b42318]">{{ error }}</p>

      <div v-if="loading" class="flex items-center gap-2 rounded-[20px] border border-white/80 bg-white/85 px-6 py-14 text-[13px] text-[#7a839a] shadow-soft">
        <LoaderCircle :size="16" class="animate-spin text-brand" /> 正在取回你的复盘…
      </div>

      <template v-else-if="!reportId">
        <div v-if="!reports.length" class="rounded-[20px] border border-dashed border-[#dfe3ee] bg-white/70 px-6 py-16 text-center shadow-soft">
          <FileText :size="28" class="mx-auto mb-3 text-brand/60" />
          <p class="text-[15px] font-medium text-ink">还没有复盘记录</p>
          <p class="mt-1.5 text-[13px] text-[#8b93a7]">回到对话页交给我一份对话文件，就能生成第一份看得见的复盘</p>
          <button type="button" class="btn small mt-5" @click="router.push({ name: 'home' })">去对话</button>
        </div>

        <div v-else class="space-y-4">
          <div class="grid gap-3 sm:grid-cols-2">
            <button
              v-for="report in reports"
              :key="report.id"
              type="button"
              class="group rounded-[18px] border border-white/80 bg-white/85 p-5 text-left shadow-soft backdrop-blur-sm transition-all hover:-translate-y-0.5 hover:border-brand/30"
              @click="openReport(report.id)"
            >
              <div class="mb-3 flex items-center justify-between gap-2">
                <p class="text-[15px] font-semibold text-ink">{{ friendlyDate(report.created_at) }}</p>
                <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="report.status === 'DONE' ? 'bg-teal-50 text-[#0f766e]' : 'bg-[#fff5e6] text-[#b45309]'">
                  {{ friendlyReportStatus(report.status) }}
                </span>
              </div>
              <div class="flex flex-wrap gap-2 text-[11px] text-[#5b6478]">
                <span class="rounded-full bg-[#f1f4f9] px-2.5 py-1">回看 {{ Number(report.overview?.dialogue_count) || 0 }} 段对话</span>
                <span class="rounded-full bg-[#f1f4f9] px-2.5 py-1">{{ sectionItems(report, 'key_event').length }} 件值得回看</span>
                <span class="rounded-full bg-[#f1f4f9] px-2.5 py-1">{{ report.action_items.length }} 个行动项</span>
              </div>
              <p v-if="comparisonText(report)" class="mt-3 line-clamp-2 text-[12px] leading-relaxed text-[#7a839a]">
                {{ comparisonText(report) }}
              </p>
              <p class="mt-4 flex items-center gap-1 text-[12px] font-semibold text-brand">
                打开看看 <ArrowRight :size="13" class="transition-transform group-hover:translate-x-0.5" />
              </p>
            </button>
          </div>

          <section v-if="trend.length > 1" class="rounded-[20px] border border-white/80 bg-white/85 p-6 shadow-soft">
            <div class="mb-3 flex items-center gap-2">
              <BarChart3 :size="16" class="text-brand" />
              <h2 class="text-[16px] font-semibold text-ink">回看的对话数变化</h2>
            </div>
            <svg viewBox="0 0 300 80" class="h-24 w-full" preserveAspectRatio="none">
              <line x1="20" y1="70" x2="280" y2="70" stroke="#e4e8f0" stroke-width="1" />
              <polyline :points="trendChart.line" fill="none" stroke="#4f46e5" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
              <circle v-for="(dot, index) in trendChart.dots" :key="index" :cx="dot.x" :cy="dot.y" r="3.5" fill="#14b8a6" />
            </svg>
            <div class="mt-2 flex justify-between text-[11px] text-[#9aa2b4]">
              <span>{{ trend[0].label }}</span>
              <span>最多 {{ trendChart.max }} 段</span>
              <span>{{ trend[trend.length - 1].label }}</span>
            </div>
          </section>
        </div>
      </template>

      <template v-else-if="current">
        <div class="mb-5 flex flex-wrap gap-2">
          <a href="#section-overview" class="rounded-full bg-white/80 px-3.5 py-1.5 text-[12px] font-medium text-[#5b6478] shadow-sm hover:text-brand">数据概览</a>
          <a href="#section-events" class="rounded-full bg-white/80 px-3.5 py-1.5 text-[12px] font-medium text-[#5b6478] shadow-sm hover:text-brand">关键事件与判断</a>
          <a href="#section-changes" class="rounded-full bg-white/80 px-3.5 py-1.5 text-[12px] font-medium text-[#5b6478] shadow-sm hover:text-brand">想法的变化</a>
          <a href="#section-actions" class="rounded-full bg-white/80 px-3.5 py-1.5 text-[12px] font-medium text-[#5b6478] shadow-sm hover:text-brand">行动跟踪</a>
        </div>

        <p v-if="current.status !== 'DONE'" class="mb-4 rounded-[14px] border border-[#b45309]/20 bg-[#fff9ee] px-4 py-3 text-[13px] leading-relaxed text-[#7a4a12]">
          这次复盘没能完整生成，下面只保留已经记下来的部分。可以回到对话页换个模型再试一次。
        </p>

        <div class="space-y-4">
          <section id="section-overview" class="scroll-mt-24 rounded-[20px] border border-white/80 bg-white/85 p-6 shadow-soft backdrop-blur-sm">
            <div class="mb-5">
              <h2 class="text-[17px] font-semibold text-ink">这一段做了什么</h2>
              <p class="mt-1 text-[12px] text-[#9aa2b4]">先看全貌，再看细节</p>
            </div>
            <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              <div class="rounded-[14px] bg-[#f8fafc] px-4 py-3.5">
                <p class="text-[24px] font-semibold text-brand">{{ stats.dialogueCount }}</p>
                <p class="mt-1 text-[11px] text-[#8b93a7]">回看的对话</p>
              </div>
              <div class="rounded-[14px] bg-[#f8fafc] px-4 py-3.5">
                <p class="text-[24px] font-semibold text-brand">{{ stats.keyEvents }}</p>
                <p class="mt-1 text-[11px] text-[#8b93a7]">值得回看的事</p>
              </div>
              <div class="rounded-[14px] bg-[#f8fafc] px-4 py-3.5">
                <p class="text-[24px] font-semibold text-brand">{{ stats.judgments }}</p>
                <p class="mt-1 text-[11px] text-[#8b93a7]">判断复盘</p>
              </div>
              <div class="rounded-[14px] bg-[#f8fafc] px-4 py-3.5">
                <p class="text-[24px] font-semibold text-brand">{{ stats.changes }}</p>
                <p class="mt-1 text-[11px] text-[#8b93a7]">想法的变化</p>
              </div>
            </div>

            <p v-if="comparison" class="mt-4 flex items-start gap-2 rounded-[14px] bg-brand/5 px-4 py-3 text-[13px] leading-relaxed text-[#434c60]">
              <Sparkles :size="15" class="mt-0.5 shrink-0 text-brand" /> {{ comparison }}
            </p>
            <p v-else class="mt-4 rounded-[14px] bg-[#f8fafc] px-4 py-3 text-[13px] text-[#8b93a7]">这次还没有可比的上一段记录，多记几次就能看出变化。</p>

            <div v-if="domainBars.length || topicBars.length" class="mt-5 grid gap-5 sm:grid-cols-2">
              <div v-if="domainBars.length">
                <p class="mb-3 text-[12px] font-semibold text-[#5b6478]">讨论集中在哪些方向</p>
                <div class="space-y-2.5">
                  <div v-for="(bar, index) in domainBars" :key="`domain-${index}`" class="flex items-center gap-2.5">
                    <span class="w-20 shrink-0 truncate text-[12px] text-[#5b6478]">{{ bar.label }}</span>
                    <div class="progress flex-1"><div :style="{ width: `${bar.percent}%` }"></div></div>
                    <span class="w-9 shrink-0 text-right text-[11px] text-[#9aa2b4]">{{ bar.count }} 段</span>
                  </div>
                </div>
              </div>
              <div v-if="topicBars.length">
                <p class="mb-3 text-[12px] font-semibold text-[#5b6478]">精力花在了哪些事上</p>
                <div class="space-y-2.5">
                  <div v-for="(bar, index) in topicBars" :key="`topic-${index}`" class="flex items-center gap-2.5">
                    <span class="w-20 shrink-0 truncate text-[12px] text-[#5b6478]">{{ bar.label }}</span>
                    <div class="progress flex-1"><div :style="{ width: `${bar.percent}%` }"></div></div>
                    <span class="w-9 shrink-0 text-right text-[11px] text-[#9aa2b4]">{{ bar.count }} 次</span>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="trend.length > 1" class="mt-6 border-t border-[#eef0f6] pt-5">
              <div class="mb-2 flex items-center gap-2">
                <BarChart3 :size="15" class="text-brand" />
                <p class="text-[12px] font-semibold text-[#5b6478]">回看对话数的趋势</p>
              </div>
              <svg viewBox="0 0 300 80" class="h-20 w-full" preserveAspectRatio="none">
                <line x1="20" y1="70" x2="280" y2="70" stroke="#e4e8f0" stroke-width="1" />
                <polyline :points="trendChart.line" fill="none" stroke="#4f46e5" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
                <circle v-for="(dot, index) in trendChart.dots" :key="index" :cx="dot.x" :cy="dot.y" r="3.5" fill="#14b8a6" />
              </svg>
              <div class="flex justify-between text-[11px] text-[#9aa2b4]">
                <span>{{ trend[0].label }}</span>
                <span>{{ trend[trend.length - 1].label }}</span>
              </div>
            </div>
          </section>

          <section id="section-events" class="scroll-mt-24 rounded-[20px] border border-white/80 bg-white/85 p-6 shadow-soft backdrop-blur-sm">
            <div class="mb-5">
              <h2 class="text-[17px] font-semibold text-ink">值得回看的几件事</h2>
              <p class="mt-1 text-[12px] text-[#9aa2b4]">当时怎么想、后来怎么样，都摆在一起看</p>
            </div>

            <div v-if="keyEvents.length" class="space-y-3">
              <article v-for="(item, index) in keyEvents" :key="item.id" class="rounded-[15px] border border-[#eef0f6] bg-[#fcfdff] p-4">
                <p class="mb-3 flex items-start gap-2 text-[14px] font-semibold leading-relaxed text-ink">
                  <span class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[11px] text-brand">{{ index + 1 }}</span>
                  {{ text(item.payload, 'background') }}
                </p>
                <div class="grid gap-2 sm:grid-cols-2">
                  <div v-if="text(item.payload, 'my_judgment')" class="rounded-[12px] bg-white px-3 py-2.5">
                    <p class="mb-1 text-[11px] font-semibold text-[#9aa2b4]">当时的判断</p>
                    <p class="text-[13px] leading-relaxed text-[#434c60]">{{ text(item.payload, 'my_judgment') }}</p>
                  </div>
                  <div v-if="text(item.payload, 'actual_outcome')" class="rounded-[12px] bg-white px-3 py-2.5">
                    <p class="mb-1 text-[11px] font-semibold text-[#9aa2b4]">后来怎么样</p>
                    <p class="text-[13px] leading-relaxed text-[#434c60]">{{ text(item.payload, 'actual_outcome') }}</p>
                  </div>
                </div>
              </article>
            </div>
            <p v-else class="empty">这次没有特别标出来的事件。</p>

            <div class="mt-7">
              <h3 class="mb-1 text-[15px] font-semibold text-ink">判断与原因</h3>
              <p class="mb-4 text-[12px] text-[#9aa2b4]">这些判断准不准，你可以直接标一下</p>
              <div v-if="judgments.length" class="space-y-2.5">
                <article v-for="item in judgments" :key="item.id" class="rounded-[14px] bg-[#f8fafc] px-4 py-3.5">
                  <div class="mb-2 flex flex-wrap items-center gap-2">
                    <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="verdictTone(item.verdict)">
                      {{ friendlyVerdict(item.verdict) }}
                    </span>
                    <span v-if="friendlyAttribution(item.attribution)" class="text-[11px] text-[#8b93a7]">
                      {{ friendlyAttribution(item.attribution) }}
                    </span>
                  </div>
                  <p class="text-[13px] leading-relaxed text-[#434c60]">{{ text(item.payload, 'reason') }}</p>
                  <div class="mt-3 flex flex-wrap items-center gap-2">
                    <template v-if="!item.feedback?.decision">
                      <button type="button" class="btn ghost small" :disabled="busyId !== null" @click="giveFeedback(item, 'AGREE')">
                        <ThumbsUp :size="13" class="mr-1 inline" /> 认同
                      </button>
                      <button type="button" class="btn ghost small" :disabled="busyId !== null" @click="giveFeedback(item, 'DISAGREE')">
                        <ThumbsDown :size="13" class="mr-1 inline" /> 不太对
                      </button>
                    </template>
                    <span v-else class="inline-flex items-center gap-1 text-[11px] font-medium text-[#0f766e]">
                      <Check :size="12" /> 你标记了「{{ item.feedback.decision === 'AGREE' ? '认同' : '不太对' }}」
                    </span>
                  </div>
                </article>
              </div>
              <p v-else class="empty">这次没有需要复核的判断。</p>
            </div>
          </section>

          <section id="section-changes" class="scroll-mt-24 rounded-[20px] border border-white/80 bg-white/85 p-6 shadow-soft backdrop-blur-sm">
            <div class="mb-5">
              <h2 class="text-[17px] font-semibold text-ink">想法的转变</h2>
              <p class="mt-1 text-[12px] text-[#9aa2b4]">比学会一件具体的事更值得记下来的，是看法变了</p>
            </div>
            <div v-if="changes.length" class="space-y-3">
              <div class="mb-1 flex items-start gap-2 rounded-[14px] bg-[#f0fbf8] px-4 py-3 text-[13px] leading-relaxed text-[#0f766e]">
                <Lightbulb :size="15" class="mt-0.5 shrink-0" />
                这段时间有 {{ changes.length }} 处想法调整，回看时可以先从这几条开始。
              </div>
              <article v-for="item in changes" :key="item.id" class="grid gap-3 rounded-[15px] border border-[#eef0f6] p-4 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
                <div class="rounded-[12px] bg-[#f8fafc] px-3.5 py-3">
                  <p class="mb-1 text-[11px] font-semibold text-[#9aa2b4]">以前这么想</p>
                  <p class="text-[13px] leading-relaxed text-[#5b6478]">{{ text(item.payload, 'old_belief') }}</p>
                </div>
                <ArrowRight :size="18" class="mx-auto rotate-90 text-brand sm:rotate-0" />
                <div class="rounded-[12px] bg-brand/5 px-3.5 py-3">
                  <p class="mb-1 text-[11px] font-semibold text-brand">现在更倾向</p>
                  <p class="text-[13px] leading-relaxed text-[#434c60]">{{ text(item.payload, 'new_belief') }}</p>
                </div>
              </article>
            </div>
            <p v-else class="empty">这次没有记录到明显的想法变化，继续积累几次会更清楚。</p>
          </section>

          <section id="section-actions" class="scroll-mt-24 rounded-[20px] border border-white/80 bg-white/85 p-6 shadow-soft backdrop-blur-sm">
            <div class="mb-5 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 class="text-[17px] font-semibold text-ink">接下来做什么</h2>
                <p class="mt-1 text-[12px] text-[#9aa2b4]">每条都写清了「怎么算做到」，做到了就打个勾</p>
              </div>
              <span class="text-[12px] font-medium text-[#0f766e]">已完成 {{ stats.verified }} / {{ stats.actions }}</span>
            </div>
            <div v-if="stats.actions" class="progress mb-5"><div :style="{ width: `${actionProgress}%` }"></div></div>

            <div v-if="actions.length" class="space-y-3">
              <article v-for="item in actions" :key="item.id" class="rounded-[15px] border border-[#eef0f6] bg-[#fcfdff] p-4">
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <p class="flex items-start gap-2 text-[14px] font-medium leading-relaxed text-ink">
                    <CheckCircle2 v-if="item.status === 'VERIFIED'" :size="16" class="mt-0.5 shrink-0 text-[#0f766e]" />
                    <ListChecks v-else :size="16" class="mt-0.5 shrink-0 text-brand" />
                    {{ item.content }}
                  </p>
                  <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="actionStatusTone(item.status)">
                    {{ friendlyActionStatus(item.status) }}
                  </span>
                </div>
                <p v-if="item.verification" class="mt-2.5 rounded-[12px] bg-[#f8fafc] px-3 py-2.5 text-[12px] leading-relaxed text-[#5b6478]">
                  怎么算做到：{{ item.verification }}
                </p>
                <p v-if="item.verification_note" class="mt-2 text-[12px] text-[#8b93a7]">我的记录：{{ item.verification_note }}</p>
                <div class="mt-3 flex flex-wrap items-center gap-2">
                  <input
                    v-model="noteDrafts[item.id]"
                    class="min-w-[180px] flex-1 !w-auto text-[12px]"
                    placeholder="写一句验证记录（可留空）"
                    :disabled="busyId !== null"
                  />
                  <button
                    v-if="item.status !== 'VERIFIED'"
                    type="button"
                    class="btn small"
                    :disabled="busyId !== null"
                    @click="updateAction(item, 'verify')"
                  >
                    <Check :size="13" class="mr-1 inline" /> 已经做到
                  </button>
                  <button
                    v-else
                    type="button"
                    class="btn ghost small"
                    :disabled="busyId !== null"
                    @click="updateAction(item, 'reopen')"
                  >
                    <RotateCcw :size="13" class="mr-1 inline" /> 重新打开
                  </button>
                </div>
              </article>
            </div>
            <p v-else class="empty">这次没有定下行动项。</p>
          </section>
        </div>
      </template>

      <div v-else class="rounded-[20px] border border-dashed border-[#dfe3ee] bg-white/70 px-6 py-16 text-center shadow-soft">
        <FileText :size="28" class="mx-auto mb-3 text-brand/60" />
        <p class="text-[15px] font-medium text-ink">没有找到这份复盘</p>
        <button type="button" class="btn small mt-5" @click="goBack">看看全部记录</button>
      </div>

      <p class="mt-10 text-center text-[11px] text-[#b0b6c4]">记录留在这里，随时回来对照自己走过的一段路</p>
    </div>
  </div>
</template>
