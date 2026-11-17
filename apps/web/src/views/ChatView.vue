<script setup lang="ts">
import { ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { RetrievalAskResponse, RetrievalItem } from '../types'

const query = ref('')
const provider = ref('deepseek')
const profileAware = ref(true)
const domain = ref('')
const platform = ref('')
const verdict = ref('')
const answer = ref('')
const sources = ref<RetrievalItem[]>([])
const profileUsed = ref(false)
const error = ref('')
const busy = ref(false)
const indexed = ref(0)

function message(err: unknown): string {
  return err instanceof ApiError ? err.body?.message || err.message : '操作失败'
}

async function buildIndex(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    const result = await api.post<{ indexed: number }>('/retrieval/index', {
      provider: provider.value,
      limit: 500,
    })
    indexed.value = result.indexed
  } catch (err) {
    error.value = message(err)
  } finally {
    busy.value = false
  }
}

async function ask(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    const filters: Record<string, string> = {}
    if (domain.value) filters.domain = domain.value
    if (platform.value) filters.platform = platform.value
    if (verdict.value) filters.verdict = verdict.value
    const result = await api.post<RetrievalAskResponse>('/retrieval/ask', {
      query: query.value,
      provider: provider.value,
      profile_aware: profileAware.value,
      filters,
      top_k: 8,
    })
    answer.value = result.answer
    sources.value = result.sources
    profileUsed.value = result.profile_used
  } catch (err) {
    error.value = message(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="grid two">
    <div class="card">
      <div class="card-head">
        <div>
          <h2>向成长档案提问</h2>
          <p>只基于已抽取的碎片回答；证据不足会说不知道。</p>
        </div>
        <button class="btn ghost small" :disabled="busy" @click="buildIndex">建立索引</button>
      </div>

      <div class="field">
        <label>问题</label>
        <textarea v-model="query" style="min-height: 110px" placeholder="例如：我在分页方案上更倾向于什么？"></textarea>
      </div>

      <div class="grid three">
        <div class="field">
          <label>领域</label>
          <input v-model="domain" placeholder="backend" />
        </div>
        <div class="field">
          <label>平台</label>
          <input v-model="platform" placeholder="markdown" />
        </div>
        <div class="field">
          <label>判断</label>
          <select v-model="verdict">
            <option value="">全部</option>
            <option value="CORRECT">CORRECT</option>
            <option value="PARTIAL">PARTIAL</option>
            <option value="WRONG">WRONG</option>
            <option value="UNVERIFIED">UNVERIFIED</option>
          </select>
        </div>
      </div>

      <div class="row spread" style="margin-top: 6px">
        <label class="row muted" style="gap: 6px">
          <input v-model="profileAware" type="checkbox" style="width: auto" />
          结合当前画像
        </label>
        <select v-model="provider" style="width: 170px">
          <option value="deepseek">DeepSeek</option>
          <option value="volcengine">火山引擎</option>
          <option value="hunyuan">混元</option>
          <option value="openai_compat">兼容端点</option>
        </select>
      </div>

      <button class="btn" style="margin-top: 16px; width: 100%" :disabled="busy" @click="ask">
        {{ busy ? '检索中…' : '提问' }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="indexed" class="muted" style="margin-top: 10px">本次新增向量 {{ indexed }} 条。</p>
    </div>

    <div>
      <div class="card">
        <div class="card-head">
          <div>
            <h2>回答</h2>
            <p v-if="profileUsed">已结合当前画像摘要</p>
            <p v-else>未使用画像</p>
          </div>
        </div>
        <div v-if="!answer" class="empty">还没有回答</div>
        <div v-else class="message reply">{{ answer }}</div>
      </div>

      <div v-if="sources.length" class="card">
        <div class="card-head">
          <div>
            <h2>引用来源</h2>
            <p>按 RRF 融合排序</p>
          </div>
        </div>
        <div class="list">
          <div v-for="item in sources" :key="item.fragment_id" class="list-item">
            <div class="row spread">
              <strong>#{{ item.fragment_id }} · {{ item.kind }}</strong>
              <span class="badge blue">RRF {{ item.score }}</span>
            </div>
            <p style="margin-top: 8px">{{ JSON.stringify(item.payload) }}</p>
            <div class="evidence">
              <span v-if="item.domain">领域 {{ item.domain }}</span>
              <span v-if="item.platform">平台 {{ item.platform }}</span>
              <span v-if="item.rerank_score !== null">Rerank {{ item.rerank_score }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
