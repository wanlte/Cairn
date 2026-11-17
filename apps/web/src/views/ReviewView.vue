<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { ReviewReport } from '../types'

const period = ref(new Date().toISOString().slice(0, 7))
const provider = ref('deepseek')
const reports = ref<ReviewReport[]>([])
const current = ref<ReviewReport | null>(null)
const error = ref('')
const busy = ref(false)

function message(err: unknown): string {
  return err instanceof ApiError ? err.body?.message || err.message : '操作失败'
}

async function loadReports(): Promise<void> {
  reports.value = await api.get<ReviewReport[]>('/reviews')
  if (!current.value && reports.value.length) current.value = reports.value[0]
}
onMounted(loadReports)

async function generate(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    current.value = await api.post<ReviewReport>('/reviews', {
      period: period.value,
      provider: provider.value,
    })
    await loadReports()
  } catch (err) {
    error.value = message(err)
  } finally {
    busy.value = false
  }
}

async function feedback(itemId: number, decision: 'AGREE' | 'DISAGREE'): Promise<void> {
  const updated = await api.post<any>(`/reviews/items/${itemId}/feedback`, { decision })
  if (!current.value) return
  current.value = {
    ...current.value,
    items: current.value.items.map((item) => (item.id === itemId ? updated : item)),
  }
}

const judgments = computed(() =>
  (current.value?.items || []).filter((item) => item.section === 'judgment'),
)
const keyEvents = computed(() =>
  (current.value?.items || []).filter((item) => item.section === 'key_event'),
)
const changes = computed(() =>
  (current.value?.items || []).filter((item) => item.section === 'cognitive_change'),
)

function evidenceText(ids: number[]): string {
  return ids.length ? `证据 #${ids.join(' / #')}` : '无证据引用'
}

function exportMarkdown(): void {
  if (!current.value) return
  const report = current.value
  const lines = [
    `# Cairn 周复盘 · ${report.period}`,
    '',
    `模型：${report.provider || '-'} / ${report.model || '-'}`,
    `提示词版本：${report.prompt_version}`,
    '',
    '## 概览',
    JSON.stringify(report.overview, null, 2),
    '',
    '## 关键事件',
    ...keyEvents.value.map((item) => `- #${item.fragment_id} ${item.payload.background || ''}`),
    '',
    '## 对错判断',
    ...judgments.value.map(
      (item) =>
        `- **${item.verdict}** · ${item.attribution || '-'} · ${item.payload.reason || ''}（${evidenceText(item.evidence_fragment_ids)}）`,
    ),
    '',
    '## 认知变化',
    ...changes.value.map((item) => `- ${item.payload.old_belief} → ${item.payload.new_belief}`),
    '',
    '## 行动项',
    ...(report.action_items as Array<Record<string, any>>).map(
      (item) => `- [ ] ${item.content}｜验证：${item.verification}`,
    ),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `cairn-review-${report.period}.md`
  link.click()
  URL.revokeObjectURL(link.href)
}
</script>

<template>
  <div class="grid two">
    <div class="card">
      <div class="card-head">
        <div>
          <h2>生成周复盘</h2>
          <p>五段式结构，判断必须引用证据。</p>
        </div>
      </div>
      <div class="field">
        <label>周期</label>
        <input v-model="period" placeholder="2026-W47" />
      </div>
      <div class="field">
        <label>Provider</label>
        <select v-model="provider">
          <option value="deepseek">DeepSeek</option>
          <option value="volcengine">火山引擎</option>
          <option value="hunyuan">混元</option>
          <option value="openai_compat">自定义兼容端点</option>
        </select>
      </div>
      <button class="btn" :disabled="busy" @click="generate">{{ busy ? '生成中…' : '生成复盘' }}</button>
      <p v-if="error" class="error">{{ error }}</p>

      <div class="list" style="margin-top: 22px">
        <button
          v-for="item in reports"
          :key="item.id"
          class="list-item"
          :class="{ active: current?.id === item.id }"
          style="text-align: left"
          @click="current = item"
        >
          <div class="row spread">
            <strong>{{ item.period }}</strong>
            <span class="badge" :class="item.status === 'DONE' ? 'green' : 'red'">{{ item.status }}</span>
          </div>
          <p class="muted" style="margin-top: 6px">{{ item.prompt_version }} · {{ item.model || '-' }}</p>
        </button>
      </div>
    </div>

    <div v-if="current">
      <div class="card">
        <div class="card-head">
          <div>
            <h2>{{ current.period }} 复盘报告</h2>
            <p>证据不足的判断会被系统丢弃；未出结果标记 UNVERIFIED。</p>
          </div>
          <button class="btn ghost small" @click="exportMarkdown">导出 MD</button>
        </div>
        <div class="tip">
          对话 {{ (current.overview as any).dialogue_count || 0 }} 段 ·
          生成模型 {{ current.provider || '-' }} / {{ current.model || '-' }} ·
          {{ current.prompt_version }}
        </div>
      </div>

      <div v-if="current.status === 'FAILED'" class="card">
        <p class="error">生成失败：{{ current.error_code }}</p>
      </div>

      <template v-else>
        <div class="card">
          <h2>关键事件</h2>
          <div class="list" style="margin-top: 14px">
            <div v-for="item in keyEvents" :key="item.id" class="list-item">
              <strong>#{{ item.fragment_id }} {{ item.payload.background }}</strong>
              <p style="margin-top: 6px">我的判断：{{ item.payload.my_judgment }}</p>
              <p>实际结果：{{ item.payload.actual_outcome }}</p>
            </div>
          </div>
        </div>

        <div class="card">
          <h2>对错判断</h2>
          <div class="list" style="margin-top: 14px">
            <div v-for="item in judgments" :key="item.id" class="list-item">
              <div class="row spread">
                <strong>{{ item.verdict }}</strong>
                <span class="badge gray">{{ item.attribution }}</span>
              </div>
              <p style="margin-top: 8px">{{ item.payload.reason }}</p>
              <div class="evidence">
                <span v-for="id in item.evidence_fragment_ids" :key="id">#{{ id }}</span>
              </div>
              <div class="row" style="margin-top: 12px">
                <button class="btn small" :class="item.feedback?.decision === 'AGREE' ? '' : 'ghost'" @click="feedback(item.id, 'AGREE')">认同</button>
                <button class="btn small" :class="item.feedback?.decision === 'DISAGREE' ? 'danger' : 'ghost'" @click="feedback(item.id, 'DISAGREE')">不认同</button>
                <span v-if="item.feedback" class="muted">已记录反馈</span>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <h2>认知变化与行动项</h2>
          <div class="list" style="margin-top: 14px">
            <div v-for="item in changes" :key="item.id" class="list-item">
              <p>{{ item.payload.old_belief }} → <strong>{{ item.payload.new_belief }}</strong></p>
              <div class="evidence"><span v-for="id in item.evidence_fragment_ids" :key="id">#{{ id }}</span></div>
            </div>
          </div>
          <div class="list" style="margin-top: 14px">
            <div v-for="item in (current.action_items as Array<Record<string, any>>)" :key="item.id" class="list-item">
              <strong>{{ item.content }}</strong>
              <p class="muted" style="margin-top: 6px">验证：{{ item.verification }}</p>
            </div>
          </div>
        </div>
      </template>
    </div>

    <div v-else class="card empty">还没有复盘报告，先生成一份。</div>
  </div>
</template>
