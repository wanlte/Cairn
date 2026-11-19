<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { AlertTriangle, CheckCircle2, GitBranch, LoaderCircle, Sparkles } from 'lucide-vue-next'
import { ApiError, planningApi } from '../api/client'
import { workspace } from '../stores/workspace'
import type { PlanResponse } from '../types'
import { friendlyError } from '../utils/friendly'

const plan = ref<PlanResponse | null>(null)
const goal = ref('')
const week = ref(currentWeek())
const done = ref('')
const blocked = ref('')
const learning = ref('')
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const editing = ref(false)

function currentWeek(): string {
  const now = new Date()
  const start = new Date(now.getFullYear(), 0, 1)
  const days = (now.getTime() - start.getTime()) / 86400000
  const number = Math.ceil((days + start.getDay() + 1) / 7)
  return `${now.getFullYear()}-W${String(number).padStart(2, '0')}`
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    plan.value = await planningApi.current()
  } catch (err) {
    if (!(err instanceof ApiError && err.status === 404)) error.value = friendlyError(err)
  } finally {
    loading.value = false
  }
}

async function generate(): Promise<void> {
  if (goal.value.trim().length < 4) return
  busy.value = true
  error.value = ''
  try {
    const model = workspace.state.model
    plan.value = await planningApi.generate({
      goal: goal.value.trim(),
      provider: model.provider,
      model: model.model,
      credential_id: model.credentialId,
      ...(model.temporaryKey ? { temporary_api_key: model.temporaryKey } : {}),
    })
    goal.value = ''
    editing.value = false
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busy.value = false
  }
}

async function submitWeekly(): Promise<void> {
  if (!plan.value) return
  busy.value = true
  error.value = ''
  try {
    const fill = await planningApi.fillWeekly(plan.value.id, {
      week: week.value,
      done: done.value,
      blocked: blocked.value,
      learning: learning.value,
    })
    const existing = plan.value.weekly_fills.findIndex((item) => item.week === fill.week)
    if (existing >= 0) plan.value.weekly_fills.splice(existing, 1, fill)
    else plan.value.weekly_fills.push(fill)
    done.value = ''
    blocked.value = ''
    learning.value = ''
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="card animate-fade-up">
    <div class="card-head">
      <div>
        <h2 class="text-[16px] font-semibold text-ink">把目标压到能落地</h2>
        <p class="mt-1 text-[12px] text-muted">先压测可行性，再预演失败，最后留下两分钟就能开始的动作。</p>
      </div>
      <button v-if="plan && !editing" type="button" class="btn ghost small" @click="editing = true">
        换个目标
      </button>
    </div>

    <div v-if="error" class="mb-4 rounded-[12px] border border-red-100 bg-red-50 px-4 py-2.5 text-[12px] text-[#b42318]">
      {{ error }}
    </div>
    <div v-if="loading" class="flex items-center gap-2 py-6 text-[12px] text-muted">
      <LoaderCircle :size="15" class="animate-spin text-brand" /> 正在找最近的规划…
    </div>

    <template v-else-if="!plan || editing">
      <textarea
        v-model="goal"
        rows="3"
        class="w-full resize-none"
        placeholder="把想做的事写具体一点，比如：每周留出两小时验证一个小方向"
      />
      <div class="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" class="btn" :disabled="busy || goal.trim().length < 4" @click="generate">
          <LoaderCircle v-if="busy" :size="14" class="animate-spin" />
          <Sparkles v-else :size="14" />
          生成规划
        </button>
        <button v-if="editing && plan" type="button" class="btn ghost small" @click="editing = false">取消</button>
        <span class="text-[12px] text-muted">会用当前选的模型，并结合画像和最近复盘。</span>
      </div>
    </template>

    <template v-else>
      <div class="rounded-[14px] bg-gradient-to-r from-[#eef0ff] to-[#eafaf7] p-4">
        <p class="text-[11px] font-semibold text-brand">当前目标</p>
        <p class="mt-1 text-[15px] font-semibold leading-relaxed text-ink">{{ plan.goal }}</p>
      </div>

      <div v-if="plan.payload.feasibility" class="mt-5">
        <div class="mb-2 flex items-center gap-2">
          <GitBranch :size="15" class="text-brand" />
          <h3 class="text-[13px] font-semibold text-ink">可行性压测</h3>
          <span class="badge" :class="plan.payload.feasibility.verdict === '可行' ? 'green' : 'amber'">
            {{ plan.payload.feasibility.verdict }}
          </span>
        </div>
        <div class="grid gap-2 sm:grid-cols-3">
          <div class="rounded-[12px] bg-[#f8fafc] p-3">
            <p class="text-[11px] text-[#9aa2b4]">关键假设</p>
            <p class="mt-1 text-[12px] leading-relaxed text-[#434c60]">{{ plan.payload.feasibility.assumption }}</p>
          </div>
          <div class="rounded-[12px] bg-[#f8fafc] p-3">
            <p class="text-[11px] text-[#9aa2b4]">证据</p>
            <p class="mt-1 text-[12px] leading-relaxed text-[#434c60]">{{ plan.payload.feasibility.evidence }}</p>
          </div>
          <div class="rounded-[12px] bg-[#fff9ee] p-3">
            <p class="text-[11px] text-[#b45309]">风险</p>
            <p class="mt-1 text-[12px] leading-relaxed text-[#7a4a12]">{{ plan.payload.feasibility.risk }}</p>
          </div>
        </div>
      </div>

      <div v-if="plan.payload.two_minute" class="mt-5 flex items-start gap-2 rounded-[14px] border border-brand/15 bg-brand/5 p-4">
        <CheckCircle2 :size="16" class="mt-0.5 shrink-0 text-brand" />
        <div>
          <p class="text-[11px] font-semibold text-brand">两分钟版</p>
          <p class="mt-1 text-[13px] font-medium leading-relaxed text-ink">{{ plan.payload.two_minute }}</p>
        </div>
      </div>

      <div v-if="plan.payload.if_then?.length" class="mt-5">
        <h3 class="mb-2 text-[13px] font-semibold text-ink">If-then 预案</h3>
        <div class="space-y-2">
          <div v-for="(item, index) in plan.payload.if_then" :key="index" class="rounded-[12px] border border-[#eef0f6] bg-white px-3.5 py-2.5 text-[12px] leading-relaxed text-[#5b6478]">
            <b class="text-ink">如果</b> {{ item.condition }} <b class="text-brand">就</b> {{ item.action }}
          </div>
        </div>
      </div>

      <div v-if="plan.payload.premortem?.length" class="mt-5">
        <h3 class="mb-2 flex items-center gap-1.5 text-[13px] font-semibold text-ink">
          <AlertTriangle :size="14" class="text-[#b45309]" /> 先想想怎么失败
        </h3>
        <div class="grid gap-2 sm:grid-cols-2">
          <div v-for="(item, index) in plan.payload.premortem" :key="index" class="rounded-[12px] bg-[#fcfdff] p-3.5">
            <p class="text-[12px] font-semibold text-ink">{{ item.scenario }}</p>
            <p class="mt-1 text-[11px] text-[#8b93a7]">信号：{{ item.signal }}</p>
            <p class="mt-1 text-[12px] text-[#0f766e]">对策：{{ item.countermeasure }}</p>
          </div>
        </div>
      </div>

      <div v-if="plan.payload.conflicts?.length" class="mt-5">
        <h3 class="mb-2 text-[13px] font-semibold text-ink">可能互相拉扯的目标</h3>
        <div v-for="(item, index) in plan.payload.conflicts" :key="index" class="mt-2 rounded-[12px] bg-[#fff9ee] px-3.5 py-2.5 text-[12px] leading-relaxed text-[#7a4a12]">
          {{ item.goal_a }} ↔ {{ item.goal_b }}：{{ item.reason }}
        </div>
      </div>

      <div v-if="plan.payload.attribution?.length" class="mt-5">
        <h3 class="mb-2 text-[13px] font-semibold text-ink">失败归因分层</h3>
        <div class="flex flex-wrap gap-2">
          <span v-for="(item, index) in plan.payload.attribution" :key="index" class="badge gray">
            {{ item.layer }}：{{ item.explanation }}
          </span>
        </div>
      </div>

      <div class="mt-6 border-t border-[#eef0f6] pt-5">
        <h3 class="text-[13px] font-semibold text-ink">每周回填</h3>
        <p class="mt-1 text-[12px] text-muted">做到了什么、卡在哪、学到什么，写下来才算闭环。</p>
        <div class="mt-3 grid gap-2 sm:grid-cols-[140px_1fr]">
          <input v-model="week" class="text-[12px]" placeholder="如 2026-W47" />
          <div class="grid gap-2 sm:grid-cols-3">
            <input v-model="done" class="text-[12px]" placeholder="做到了什么" />
            <input v-model="blocked" class="text-[12px]" placeholder="卡在哪" />
            <input v-model="learning" class="text-[12px]" placeholder="学到什么" />
          </div>
        </div>
        <button type="button" class="btn soft small mt-3" :disabled="busy" @click="submitWeekly">记下这一周</button>
        <div v-if="plan.weekly_fills.length" class="list mt-4">
          <div v-for="fill in plan.weekly_fills" :key="fill.id" class="list-item text-[12px]">
            <p class="font-semibold text-ink">{{ fill.week }}</p>
            <p v-if="fill.done" class="mt-1 text-[#0f766e]">做到：{{ fill.done }}</p>
            <p v-if="fill.blocked" class="mt-1 text-[#b45309]">卡住：{{ fill.blocked }}</p>
            <p v-if="fill.learning" class="mt-1 text-muted">学到：{{ fill.learning }}</p>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
