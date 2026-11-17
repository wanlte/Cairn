<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, ApiError } from '../api/client'
import type { ConversationSummary, ExtractionRun, IngestionPreview } from '../types'

const router = useRouter()
const sourceType = ref<'markdown' | 'text' | 'deepseek_archive'>('markdown')
const text = ref('')
const fileName = ref('')
const base64 = ref('')
const error = ref('')
const busy = ref(false)
const preview = ref<IngestionPreview | null>(null)
const conversations = ref<ConversationSummary[]>([])
const corrections = ref<Record<string, { user_content?: string; assistant_content?: string }>>({})
const run = ref<ExtractionRun | null>(null)
const provider = ref('deepseek')

const progress = computed(() => {
  if (!run.value || !run.value.total) return 0
  return Math.round(((run.value.processed + run.value.failed) / run.value.total) * 100)
})

function message(err: unknown): string {
  return err instanceof ApiError ? err.body?.message || err.message : '操作失败'
}

async function onFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  fileName.value = file.name
  sourceType.value = file.name.toLowerCase().endsWith('.zip')
    ? 'deepseek_archive'
    : 'markdown'
  if (sourceType.value === 'deepseek_archive') {
    const buffer = await file.arrayBuffer()
    const bytes = new Uint8Array(buffer)
    let binary = ''
    bytes.forEach((byte) => (binary += String.fromCharCode(byte)))
    base64.value = btoa(binary)
    text.value = ''
  } else {
    text.value = await file.text()
    base64.value = ''
  }
}

async function loadConversations(): Promise<void> {
  const result = await api.get<{ items: ConversationSummary[] }>('/ingestion/conversations')
  conversations.value = result.items
}
onMounted(loadConversations)

async function createPreview(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    preview.value = await api.post<IngestionPreview>('/ingestion/preview', {
      source_type: sourceType.value,
      text: sourceType.value === 'deepseek_archive' ? undefined : text.value,
      base64: sourceType.value === 'deepseek_archive' ? base64.value : undefined,
      filename: fileName.value || undefined,
    })
    corrections.value = {}
  } catch (err) {
    error.value = message(err)
  } finally {
    busy.value = false
  }
}

async function commit(): Promise<void> {
  if (!preview.value) return
  busy.value = true
  error.value = ''
  try {
    const payload = {
      preview_id: preview.value.preview_id,
      corrections: Object.entries(corrections.value)
        .filter(([id, value]) => value.user_content || value.assistant_content)
        .map(([turn_id, value]) => ({ turn_id, ...value })),
    }
    const result = await api.post<{ conversation_id: number; duplicate: boolean }>(
      '/ingestion/commit',
      payload,
    )
    preview.value = null
    await loadConversations()
    await startExtraction(result.conversation_id)
  } catch (err) {
    error.value = message(err)
  } finally {
    busy.value = false
  }
}

async function startExtraction(conversationId: number): Promise<void> {
  error.value = ''
  try {
    const created = await api.post<ExtractionRun>('/extraction/runs', {
      conversation_id: conversationId,
      provider: provider.value,
    })
    run.value = created
    await api.stream(`/extraction/runs/${created.id}/stream`, (data: ExtractionRun) => {
      run.value = data
    })
  } catch (err) {
    error.value = message(err)
  }
}
</script>

<template>
  <div class="grid two">
    <div>
      <div class="card">
        <div class="card-head">
          <div>
            <h2>导入对话</h2>
            <p>支持 Markdown / TXT 文本，以及 DeepSeek 官方 ZIP 存档。</p>
          </div>
          <span class="badge blue">不可变原始层</span>
        </div>

        <div class="field">
          <label>选择本地文件</label>
          <input type="file" accept=".md,.txt,.zip" @change="onFile" />
        </div>

        <div class="field">
          <label>或直接粘贴对话文本</label>
          <textarea v-model="text" placeholder="## 用户&#10;我的问题…&#10;&#10;## 助手&#10;回答…" :disabled="sourceType === 'deepseek_archive'"></textarea>
        </div>

        <div class="row spread">
          <div class="row">
            <label class="muted">凭证模式</label>
            <select v-model="provider" style="width: 150px">
              <option value="deepseek">DeepSeek 环境变量</option>
              <option value="volcengine">火山引擎环境变量</option>
              <option value="hunyuan">混元环境变量</option>
              <option value="openai_compat">自定义兼容端点</option>
            </select>
          </div>
          <button class="btn" :disabled="busy" @click="createPreview">
            {{ busy ? '解析中…' : '预览解析结果' }}
          </button>
        </div>
        <p v-if="error" class="error">{{ error }}</p>
      </div>

      <div v-if="preview" class="card">
        <div class="card-head">
          <div>
            <h2>{{ preview.title }}</h2>
            <p>{{ preview.total_turns }} 轮 · {{ preview.low_confidence_count }} 轮低置信 · {{ preview.source_ref }}</p>
          </div>
          <button class="btn" :disabled="busy" @click="commit">确认并抽取</button>
        </div>

        <div v-if="preview.anomalies.length" class="tip" style="margin-bottom: 16px">
          异常：{{ preview.anomalies.join('；') }}
        </div>

        <div class="list">
          <div v-for="turn in preview.turns" :key="turn.turn_id" class="list-item">
            <div class="row spread">
              <strong>轮次 {{ turn.seq }}</strong>
              <span class="badge" :class="turn.low_confidence ? 'amber' : 'green'">
                置信度 {{ turn.role_confidence.toFixed(2) }}
              </span>
            </div>
            <div class="field" style="margin-top: 12px">
              <label>用户</label>
              <textarea
                :value="turn.user_content"
                style="min-height: 74px"
                @input="corrections[turn.turn_id] = { ...corrections[turn.turn_id], user_content: ($event.target as HTMLTextAreaElement).value }"
              ></textarea>
            </div>
            <div class="field">
              <label>助手</label>
              <textarea
                :value="turn.assistant_content"
                style="min-height: 74px"
                @input="corrections[turn.turn_id] = { ...corrections[turn.turn_id], assistant_content: ($event.target as HTMLTextAreaElement).value }"
              ></textarea>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div>
      <div v-if="run" class="card">
        <div class="card-head">
          <div>
            <h2>抽取进度</h2>
            <p>{{ run.status }} · {{ run.processed }}/{{ run.total }} 轮完成 · 失败 {{ run.failed }}</p>
          </div>
          <span class="badge" :class="run.status === 'FAILED' ? 'red' : run.status === 'DONE' ? 'green' : 'blue'">
            {{ run.status }}
          </span>
        </div>
        <div class="progress"><div :style="{ width: progress + '%' }"></div></div>
        <p class="muted" style="margin-top: 10px">提示词版本 {{ run.prompt_version }}</p>
        <div v-if="run.error_json.length" class="tip" style="margin-top: 12px">
          {{ run.error_json.map((item) => `${item.turn_pair_id}: ${item.message}`).join('；') }}
        </div>
        <button v-if="run.status === 'DONE'" class="btn soft" style="margin-top: 16px" @click="router.push('/review')">
          去生成周复盘
        </button>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <h2>已导入对话</h2>
            <p>原始文本与轮次会保留，后续抽取不会覆盖。</p>
          </div>
        </div>
        <div v-if="!conversations.length" class="empty">还没有导入任何对话</div>
        <div v-else class="list">
          <div v-for="item in conversations" :key="item.id" class="list-item">
            <div class="row spread">
              <strong>{{ item.title }}</strong>
              <span class="badge gray">{{ item.source_type }}</span>
            </div>
            <p class="muted" style="margin-top: 6px">{{ item.source_ref }}</p>
            <button class="btn small soft" style="margin-top: 10px" @click="startExtraction(item.id)">
              重新抽取
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
