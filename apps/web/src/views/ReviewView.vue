<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { ActionItemRecord, ReviewReport } from '../types'

const period = ref(new Date().toISOString().slice(0, 7))
const provider = ref('deepseek')
const reports = ref<ReviewReport[]>([])
const allActions = ref<ActionItemRecord[]>([])
const current = ref<ReviewReport | null>(null)
const error = ref('')
const busy = ref(false)

function message(err: unknown): string {
  return err instanceof ApiError ? err.body?.message || err.message : '操作失败'
}

async function loadReports(): Promise<void> {
  reports.value = await api.get<ReviewReport[]>('/reviews')
  allActions.value = await api.get<ActionItemRecord[]>('/reviews/action-items')
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

async function setActionStatus(
  action: ActionItemRecord,
  status: 'verify' | 'reopen',
): Promise<void> {
  const note = window.prompt(
    status === 'verify' ? '验证备注（可选）：' : '重开原因（可选）：',
    action.verification_note || '',
  )
  const updated = await api.post<ActionItemRecord>(
    `/reviews/action-items/${action.id}/${status}`,
    { note },
  )
  allActions.value = allActions.value.map((item) =>
    item.id === updated.id ? updated : item,
  )
  if (current.value) {
    current.value = {
      ...current.value,
      action_items: current.value.action_items.map((item) =>
        item.id === updated.id ? updated : item,
      ),
    }
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

async function exportMarkdown(): Promise<void> {
  if (!current.value) return
  const markdown = await api.getText(
    `/reviews/${current.value.id}/export`,
  )
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `cairn-review-${current.value.period}.md`
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

    <div class="card">
      <div class="card-head">
        <div>
          <h2>行动项闭环</h2>
          <p>跨周保留；完成后填写验证备注，必要时可重开。</p>
        </div>
      </div>
      <div v-if="!allActions.length" class="empty">还没有行动项</div>
      <div v-else class="list">
        <div v-for="action in allActions" :key="action.id" class="list-item">
          <div class="row spread">
            <strong>{{ action.content }}</strong>
            <span class="badge" :class="action.status === 'VERIFIED' ? 'green' : 'amber'">
              {{ action.status }}
            </span>
          </div>
          <p class="muted" style="margin-top: 6px">
            {{ action.period }} · 验证标准：{{ action.verification }}
          </p>
          <p v-if="action.verification_note" class="muted" style="margin-top: 4px">
            备注：{{ action.verification_note }}
          </p>
          <div class="row" style="margin-top: 10px">
            <button
              v-if="action.status !== 'VERIFIED'"
              class="btn small"
              @click="setActionStatus(action, 'verify')"
            >
              标记完成
            </button>
            <button
              v-else
              class="btn ghost small"
              @click="setActionStatus(action, 'reopen')"
            >
              重新打开
            </button>
          </div>
        </div>
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
            <div v-for="item in current.action_items" :key="item.id" class="list-item">
              <div class="row spread">
                <strong>{{ item.content }}</strong>
                <span class="badge" :class="item.status === 'VERIFIED' ? 'green' : 'amber'">
                  {{ item.status }}
                </span>
              </div>
              <p class="muted" style="margin-top: 6px">验证：{{ item.verification }}</p>
            </div>
          </div>
        </div>
      </template>
    </div>

    <div v-else class="card empty">还没有复盘报告，先生成一份。</div>
  </div>
</template>
