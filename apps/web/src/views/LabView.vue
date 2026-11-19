<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Download, LoaderCircle, Sparkles, Users } from 'lucide-vue-next'
import { exportsApi, extensionsApi } from '../api/client'
import { workspace } from '../stores/workspace'
import type {
  DailyQuestion,
  DecisionResult,
  PairAnalysisResult,
  SimulationResult,
} from '../types'
import { friendlyError } from '../utils/friendly'

const daily = ref<DailyQuestion | null>(null)
const dailyAnswer = ref('')
const scenario = ref('')
const choice = ref('')
const simulation = ref<SimulationResult | null>(null)
const question = ref('')
const decision = ref<DecisionResult | null>(null)
const pairId = ref<number | null>(null)
const pairResult = ref<PairAnalysisResult | null>(null)
const busy = ref('')
const error = ref('')

function modelArgs() {
  const model = workspace.state.model
  return {
    provider: model.provider,
    model: model.model,
    credential_id: model.credentialId,
    ...(model.temporaryKey ? { temporary_api_key: model.temporaryKey } : {}),
  }
}

async function runDaily(): Promise<void> {
  busy.value = 'daily'
  error.value = ''
  try {
    daily.value = await extensionsApi.daily()
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busy.value = ''
  }
}

async function answerDaily(): Promise<void> {
  if (!daily.value || !dailyAnswer.value.trim()) return
  busy.value = 'daily'
  error.value = ''
  try {
    daily.value = await extensionsApi.answerDaily(daily.value.id, dailyAnswer.value.trim())
    dailyAnswer.value = ''
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busy.value = ''
  }
}

async function simulate(): Promise<void> {
  if (scenario.value.trim().length < 4) return
  busy.value = 'simulate'
  error.value = ''
  try {
    simulation.value = await extensionsApi.simulate({
      scenario: scenario.value.trim(),
      choice: choice.value.trim(),
      ...modelArgs(),
    })
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busy.value = ''
  }
}

async function decide(): Promise<void> {
  if (question.value.trim().length < 4) return
  busy.value = 'decide'
  error.value = ''
  try {
    decision.value = await extensionsApi.decide({
      question: question.value.trim(),
      ...modelArgs(),
    })
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busy.value = ''
  }
}

async function analyzePair(): Promise<void> {
  if (!pairId.value) return
  busy.value = 'pair'
  error.value = ''
  try {
    pairResult.value = await extensionsApi.pairAnalysis({
      pair_id: pairId.value,
      ...modelArgs(),
    })
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busy.value = ''
  }
}

async function download(kind: string, format: 'json' | 'md' | 'html'): Promise<void> {
  busy.value = `export-${kind}-${format}`
  error.value = ''
  try {
    const result = await exportsApi.get(kind, format)
    const blob = new Blob([result.content], {
      type: format === 'html' ? 'text/html' : 'text/plain',
    })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = result.filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busy.value = ''
  }
}

onMounted(runDaily)
</script>

<template>
  <div class="relative min-h-screen overflow-hidden bg-canvas px-5 pb-12 pt-10">
    <div class="pointer-events-none absolute -left-20 -top-20 h-72 w-72 rounded-full bg-brand-teal/10 blur-3xl" />

    <div class="relative mx-auto max-w-[1000px]">
      <div class="mb-6 flex items-center gap-3">
        <span class="flex h-11 w-11 items-center justify-center rounded-[14px] bg-gradient-to-br from-brand to-brand-teal text-white shadow-glow">
          <Sparkles :size="20" />
        </span>
        <div>
          <h1 class="text-[30px] font-semibold tracking-tight text-ink">更多玩法</h1>
          <p class="mt-0.5 text-[13px] text-muted">换个角度问问自己，也可以把结果带走。</p>
        </div>
      </div>

      <div v-if="error" class="mb-4 rounded-[14px] border border-red-100 bg-red-50 px-4 py-2.5 text-[13px] text-[#b42318]">
        {{ error }}
      </div>

      <section class="card animate-fade-up">
        <div class="card-head">
          <div>
            <h2 class="text-[16px] font-semibold text-ink">每日一问</h2>
            <p class="mt-1 text-[12px] text-muted">一天一个问题，写下真实想法就算完成。</p>
          </div>
          <span class="badge gray">{{ daily?.day || '' }}</span>
        </div>
        <p v-if="daily" class="text-[15px] font-medium leading-relaxed text-ink">{{ daily.question }}</p>
        <div v-if="daily" class="mt-3 flex flex-col gap-2 sm:flex-row">
          <input v-model="dailyAnswer" class="flex-1 text-[13px]" placeholder="今天你怎么想？" />
          <button type="button" class="btn small" :disabled="busy === 'daily' || !dailyAnswer.trim()" @click="answerDaily">
            <LoaderCircle v-if="busy === 'daily'" :size="14" class="animate-spin" /> 记下来
          </button>
        </div>
        <p v-if="daily?.answer" class="mt-3 rounded-[12px] bg-[#f4faf8] px-3.5 py-2.5 text-[13px] leading-relaxed text-[#0f766e]">
          你写道：{{ daily.answer }}
        </p>
      </section>

      <div class="mt-5 grid gap-5 md:grid-cols-2">
        <section class="card animate-fade-up">
          <h2 class="text-[16px] font-semibold text-ink">情景模拟器</h2>
          <p class="mt-1 text-[12px] text-muted">把纠结的场景写出来，看看几条路各自通向哪里。</p>
          <textarea v-model="scenario" rows="3" class="mt-4 w-full resize-none text-[13px]" placeholder="比如：要不要接下那个跨界的新项目" />
          <input v-model="choice" class="mt-2 w-full text-[12px]" placeholder="我目前倾向的选择（可选）" />
          <button type="button" class="btn small mt-3" :disabled="busy === 'simulate' || scenario.trim().length < 4" @click="simulate">
            <LoaderCircle v-if="busy === 'simulate'" :size="14" class="animate-spin" /> 推演一下
          </button>
          <div v-if="simulation" class="mt-4 space-y-2">
            <div v-for="(path, index) in simulation.payload.paths || []" :key="index" class="rounded-[12px] bg-[#f8fafc] p-3">
              <p class="text-[12px] font-semibold text-ink">{{ path.choice }}</p>
              <p class="mt-1 text-[12px] text-[#5b6478]">结果：{{ path.outcome }}</p>
              <p class="mt-1 text-[11px] text-[#0f766e]">留意信号：{{ path.signal }}</p>
            </div>
            <p v-if="simulation.payload.advice" class="tip">{{ simulation.payload.advice }}</p>
          </div>
        </section>

        <section class="card animate-fade-up">
          <h2 class="text-[16px] font-semibold text-ink">决策代理</h2>
          <p class="mt-1 text-[12px] text-muted">把此刻的犹豫交给它，先拿到一个能执行的建议。</p>
          <textarea v-model="question" rows="3" class="mt-4 w-full resize-none text-[13px]" placeholder="比如：先做哪件事最不容易后悔？" />
          <button type="button" class="btn small mt-3" :disabled="busy === 'decide' || question.trim().length < 4" @click="decide">
            <LoaderCircle v-if="busy === 'decide'" :size="14" class="animate-spin" /> 给个建议
          </button>
          <div v-if="decision" class="mt-4 rounded-[14px] bg-gradient-to-r from-[#eef0ff] to-[#eafaf7] p-4">
            <p class="text-[13px] font-semibold leading-relaxed text-ink">{{ decision.suggestion }}</p>
            <ul class="mt-2 space-y-1">
              <li v-for="(reason, index) in decision.reasons" :key="index" class="text-[12px] text-[#5b6478]">· {{ reason }}</li>
            </ul>
            <p class="mt-3 text-[12px] font-medium text-brand">第一步：{{ decision.first_step }}</p>
          </div>
        </section>
      </div>

      <section class="card mt-5 animate-fade-up">
        <div class="flex items-center gap-2">
          <Users :size="17" class="text-brand" />
          <h2 class="text-[16px] font-semibold text-ink">双人授权分析</h2>
        </div>
        <p class="mt-1 text-[12px] text-muted">双方都同意后，看的是冲突时怎么错位，不是合不合适。</p>
        <div class="mt-4 flex flex-col gap-2 sm:flex-row">
          <input v-model.number="pairId" type="number" class="flex-1 text-[12px]" placeholder="已确认的关系编号" />
          <button type="button" class="btn small" :disabled="busy === 'pair' || !pairId" @click="analyzePair">
            <LoaderCircle v-if="busy === 'pair'" :size="14" class="animate-spin" /> 看看错位点
          </button>
        </div>
        <div v-if="pairResult" class="mt-4">
          <p class="text-[13px] font-medium text-ink">{{ pairResult.summary }}</p>
          <div v-for="(item, index) in pairResult.mismatches" :key="index" class="mt-3 rounded-[12px] border border-[#eef0f6] p-3.5">
            <p class="text-[12px] font-semibold text-ink">{{ item.situation }}</p>
            <p class="mt-1 text-[12px] text-[#5b6478]">你：{{ item.you }}｜对方：{{ item.them }}</p>
            <p class="mt-1 text-[12px] text-[#0f766e]">补偿：{{ item.repair }}</p>
          </div>
        </div>
      </section>

      <section class="card mt-5 animate-fade-up">
        <h2 class="text-[16px] font-semibold text-ink">把结果带走</h2>
        <p class="mt-1 text-[12px] text-muted">JSON 方便再做处理，Markdown 方便记笔记，HTML 打开后可以打印成 PDF。</p>
        <div class="mt-4 flex flex-wrap gap-2">
          <template v-for="kind in ['profile', 'review', 'plan']" :key="kind">
            <button
              v-for="format in ['json', 'md', 'html']"
              :key="`${kind}-${format}`"
              type="button"
              class="btn ghost small"
              :disabled="busy.startsWith('export-')"
              @click="download(kind, format as 'json' | 'md' | 'html')"
            >
              <Download :size="13" class="mr-1 inline" />
              {{ kind === 'profile' ? '画像' : kind === 'review' ? '复盘' : '规划' }} · {{ format }}
            </button>
          </template>
        </div>
      </section>
    </div>
  </div>
</template>
