<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Database, LoaderCircle, RefreshCw } from 'lucide-vue-next'
import { analysisApi, insightsApi, samplesApi, timelineApi } from '../api/client'
import type {
  Coverage,
  DesirabilityFlag,
  DriftCurve,
  RelationGraph,
  TimelineEvent,
} from '../types'
import { friendlyError } from '../utils/friendly'
import SampleCoverageCard from '../components/SampleCoverageCard.vue'
import CounterfactualForm from '../components/CounterfactualForm.vue'
import SourceImportPanel from '../components/SourceImportPanel.vue'
import TimelineList from '../components/TimelineList.vue'
import DriftCurveCard from '../components/DriftCurve.vue'
import RelationGraphCard from '../components/RelationGraph.vue'
import PlanBoard from '../components/PlanBoard.vue'

type Tab =
  | 'coverage'
  | 'counterfactual'
  | 'import'
  | 'timeline'
  | 'desirability'
  | 'drift'
  | 'graph'
  | 'plan'
const tabs: { key: Tab; label: string }[] = [
  { key: 'coverage', label: '样本体检' },
  { key: 'counterfactual', label: '反事实补录' },
  { key: 'import', label: '多源导入' },
  { key: 'timeline', label: '时间线' },
  { key: 'desirability', label: '表达提醒' },
  { key: 'drift', label: '变化曲线' },
  { key: 'graph', label: '关系图' },
  { key: 'plan', label: '行动规划' },
]

const tab = ref<Tab>('coverage')
const coverage = ref<Coverage | null>(null)
const events = ref<TimelineEvent[]>([])
const flags = ref<DesirabilityFlag[]>([])
const curve = ref<DriftCurve>({ points: [], total_snapshots: 0 })
const graph = ref<RelationGraph>({ nodes: [], edges: [] })
const lowPrecisionCount = ref(0)
const loading = ref(false)
const error = ref('')

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [sample, timeline, desirability, drift, relations] = await Promise.all([
      samplesApi.coverage(),
      timelineApi.events(undefined, 200),
      analysisApi.desirability(),
      insightsApi.drift(),
      insightsApi.graph(),
    ])
    coverage.value = sample
    events.value = timeline.items
    flags.value = desirability
    curve.value = drift
    graph.value = relations
    lowPrecisionCount.value = timeline.low_precision_count
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    loading.value = false
  }
}

async function rebuildGraph(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    await insightsApi.rebuildGraph()
    graph.value = await insightsApi.graph()
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="relative min-h-screen overflow-hidden bg-canvas px-5 pb-12 pt-10">
    <div class="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-brand/10 blur-3xl" />
    <div class="pointer-events-none absolute -left-20 top-40 h-64 w-64 rounded-full bg-brand-teal/10 blur-3xl" />

    <div class="relative mx-auto max-w-[1000px]">
      <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <span class="flex h-11 w-11 items-center justify-center rounded-[14px] bg-gradient-to-br from-brand to-brand-teal text-white shadow-glow">
            <Database :size="20" />
          </span>
          <div>
            <h1 class="text-[30px] font-semibold tracking-tight text-ink">数据与样本</h1>
            <p class="mt-0.5 text-[13px] text-muted">先看清手里的记录，再谈分析和规划。</p>
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            v-if="tab === 'graph'"
            type="button"
            class="btn ghost small"
            :disabled="loading"
            @click="rebuildGraph"
          >
            <RefreshCw :size="14" class="mr-1 inline" /> 重建关系
          </button>
          <button type="button" class="btn ghost small" :disabled="loading" @click="load">
            <LoaderCircle v-if="loading" :size="14" class="animate-spin" />
            <RefreshCw v-else :size="14" />
            重新检查
          </button>
        </div>
      </div>

      <div v-if="error" class="mb-4 rounded-[14px] border border-red-100 bg-red-50 px-4 py-2.5 text-[13px] text-[#b42318]">
        {{ error }}
      </div>

      <nav class="mb-5 flex flex-wrap gap-2 rounded-full bg-white/70 p-1.5 shadow-soft backdrop-blur-sm">
        <button
          v-for="item in tabs"
          :key="item.key"
          type="button"
          class="rounded-full px-4 py-2 text-[13px] font-semibold transition-all"
          :class="tab === item.key ? 'bg-brand text-white shadow-sm' : 'text-[#667085] hover:text-ink'"
          @click="tab = item.key"
        >
          {{ item.label }}
        </button>
      </nav>

      <SampleCoverageCard v-if="tab === 'coverage'" :coverage="coverage" :loading="loading" />
      <CounterfactualForm v-else-if="tab === 'counterfactual'" />
      <SourceImportPanel v-else-if="tab === 'import'" @imported="load" />
      <TimelineList v-else-if="tab === 'timeline'" :events="events" :low-precision-count="lowPrecisionCount" />
      <DriftCurveCard v-else-if="tab === 'drift'" :points="curve.points" />
      <RelationGraphCard v-else-if="tab === 'graph'" :graph="graph" />
      <PlanBoard v-else-if="tab === 'plan'" />
      <section v-else class="card animate-fade-up">
        <div class="card-head">
          <div>
            <h2 class="text-[16px] font-semibold text-ink">表达提醒</h2>
            <p class="mt-1 text-[12px] text-muted">这些记录里有些「应该怎么说」的痕迹，值得再想想真实想法。</p>
          </div>
          <span class="badge amber">{{ flags.length }} 条</span>
        </div>
        <div v-if="flags.length" class="list">
          <div v-for="flag in flags" :key="flag.fragment_id" class="list-item">
            <div class="flex items-center gap-2">
              <span class="badge amber">痕迹强度 {{ Math.round(flag.score * 100) }}%</span>
              <span class="text-[11px] text-muted">记录 #{{ flag.fragment_id }}</span>
            </div>
            <p class="mt-2 text-[13px] text-ink">{{ flag.summary }}</p>
            <div class="evidence">
              <span v-for="signal in flag.signals" :key="signal">{{ signal }}</span>
            </div>
          </div>
        </div>
        <div v-else class="empty">没有发现明显的表达偏差，挺好的。</div>
      </section>
    </div>
  </div>
</template>
