<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { LoaderCircle, RefreshCw, Stethoscope, Trophy } from 'lucide-vue-next'
import { metricsApi } from '../api/client'
import type { MetricsOverview } from '../types'
import { friendlyError } from '../utils/friendly'
import MetricsDiagnostic from '../components/MetricsDiagnostic.vue'
import MetricsValue from '../components/MetricsValue.vue'

type View = 'diagnostic' | 'value'

const data = ref<MetricsOverview | null>(null)
const view = ref<View>('diagnostic')
const windowDays = ref(30)
const loading = ref(false)
const error = ref('')

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    data.value = await metricsApi.overview(windowDays.value)
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
    <div class="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-brand/10 blur-3xl" />

    <div class="relative mx-auto max-w-[1000px]">
      <div class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-[30px] font-semibold tracking-tight text-ink">项目评测</h1>
          <p class="mt-0.5 text-[13px] text-muted">从快、准、成本到用户旅程，看清楚项目走到了哪一步。</p>
        </div>
        <div class="flex items-center gap-2">
          <select v-model.number="windowDays" class="text-[12px]" @change="load">
            <option :value="7">最近 7 天</option>
            <option :value="30">最近 30 天</option>
            <option :value="90">最近 90 天</option>
          </select>
          <button type="button" class="btn ghost small" :disabled="loading" @click="load">
            <RefreshCw :size="14" :class="loading ? 'animate-spin' : ''" />
            刷新
          </button>
        </div>
      </div>

      <div class="mb-5 flex gap-2 rounded-full bg-[#eef0f6] p-1">
        <button
          type="button"
          class="flex flex-1 items-center justify-center gap-2 rounded-full px-4 py-2 text-[13px] font-semibold transition"
          :class="view === 'diagnostic' ? 'bg-white text-brand shadow-sm' : 'text-muted hover:text-ink'"
          @click="view = 'diagnostic'"
        >
          <Stethoscope :size="15" /> 内部诊断
        </button>
        <button
          type="button"
          class="flex flex-1 items-center justify-center gap-2 rounded-full px-4 py-2 text-[13px] font-semibold transition"
          :class="view === 'value' ? 'bg-white text-brand shadow-sm' : 'text-muted hover:text-ink'"
          @click="view = 'value'"
        >
          <Trophy :size="15" /> 对外价值
        </button>
      </div>

      <div v-if="error" class="mb-4 rounded-[14px] border border-red-100 bg-red-50 px-4 py-2.5 text-[13px] text-[#b42318]">
        {{ error }}
      </div>
      <div v-if="loading && !data" class="card flex items-center justify-center gap-2 py-16 text-[13px] text-muted">
        <LoaderCircle :size="16" class="animate-spin text-brand" /> 正在汇总各项指标…
      </div>
      <MetricsDiagnostic v-else-if="data && view === 'diagnostic'" :data="data" />
      <MetricsValue v-else-if="data" :data="data" />
    </div>
  </div>
</template>
