<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { Credential, UsageRow } from '../types'

const credentials = ref<Credential[]>([])
const capabilities = ref<any>({ known: [], probed: [] })
const usage = ref<UsageRow[]>([])
const calls = ref<any[]>([])
const error = ref('')
const busy = ref(false)

const form = ref({
  name: '',
  provider: 'deepseek',
  api_key: '',
  base_url: '',
  model: '',
})

function message(err: unknown): string {
  return err instanceof ApiError ? err.body?.message || err.message : '操作失败'
}

async function load(): Promise<void> {
  credentials.value = await api.get<Credential[]>('/credentials')
  capabilities.value = await api.get('/credentials/capabilities')
  usage.value = (await api.get<{ items: UsageRow[] }>('/usage/summary')).items
  calls.value = (await api.get<{ items: any[] }>('/usage/calls?limit=20')).items
}
onMounted(load)

async function create(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    await api.post('/credentials', form.value, { 'X-Confirm-Action': 'confirm' })
    form.value = { name: '', provider: 'deepseek', api_key: '', base_url: '', model: '' }
    await load()
  } catch (err) {
    error.value = message(err)
  } finally {
    busy.value = false
  }
}

async function test(id: number): Promise<void> {
  await api.post(`/credentials/${id}/test`)
  await load()
}

async function remove(id: number): Promise<void> {
  if (!window.confirm('删除后不可恢复，确认删除该凭证？')) return
  await api.delete(`/credentials/${id}`, { 'X-Confirm-Action': 'confirm' })
  await load()
}
</script>

<template>
  <div class="grid two">
    <div>
      <div class="card">
        <div class="card-head">
          <div>
            <h2>凭证模式</h2>
            <p>单用户本地部署推荐环境变量；多用户共享服务推荐加密凭证。</p>
          </div>
          <span class="badge green">密钥不明文回显</span>
        </div>
        <div class="tip">
          环境变量模式：把 <strong>DEEPSEEK_API_KEY</strong> 等写入本机 <strong>.env</strong>（已忽略），
          前端只传 provider，密钥不经过 API、不落库。适合你自己用。<br />
          加密凭证模式：密钥通过 Fernet 加密后存数据库，按用户隔离；API 只返回掩码。适合多用户。
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <h2>添加加密凭证</h2>
            <p>需要二次确认头，前端已自动附加。</p>
          </div>
        </div>
        <div class="grid two">
          <div class="field">
            <label>名称</label>
            <input v-model="form.name" placeholder="my-deepseek" />
          </div>
          <div class="field">
            <label>Provider</label>
            <select v-model="form.provider">
              <option value="deepseek">deepseek</option>
              <option value="volcengine">volcengine</option>
              <option value="hunyuan">hunyuan</option>
              <option value="openai_compat">openai_compat</option>
            </select>
          </div>
          <div class="field">
            <label>API Key</label>
            <input v-model="form.api_key" type="password" placeholder="sk-..." />
          </div>
          <div class="field">
            <label>Base URL（可选）</label>
            <input v-model="form.base_url" placeholder="https://..." />
          </div>
          <div class="field">
            <label>模型（可选）</label>
            <input v-model="form.model" placeholder="deepseek-chat" />
          </div>
        </div>
        <button class="btn" :disabled="busy" @click="create">添加凭证</button>
        <p v-if="error" class="error">{{ error }}</p>
      </div>

      <div class="card">
        <h2>凭证列表</h2>
        <div v-if="!credentials.length" class="empty" style="margin-top: 14px">还没有添加凭证</div>
        <div v-else class="list" style="margin-top: 14px">
          <div v-for="item in credentials" :key="item.id" class="list-item">
            <div class="row spread">
              <strong>{{ item.name }}</strong>
              <span class="badge blue">{{ item.provider }}</span>
            </div>
            <p class="muted" style="margin-top: 6px">{{ item.api_key_masked }} · {{ item.model || '默认模型' }}</p>
            <div class="row" style="margin-top: 10px">
              <button class="btn ghost small" @click="test(item.id)">探测能力</button>
              <button class="btn danger small" @click="remove(item.id)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div>
      <div class="card">
        <h2>能力矩阵</h2>
        <p class="muted">已知矩阵来自内置快照；探测结果会缓存在服务端。</p>
        <div class="list" style="margin-top: 14px">
          <div v-for="item in capabilities.known" :key="item.provider" class="list-item">
            <div class="row spread">
              <strong>{{ item.provider }}</strong>
              <span class="badge" :class="item.json_schema ? 'green' : 'amber'">
                {{ item.json_schema ? 'JSON Schema' : item.structured_output }}
              </span>
            </div>
            <p class="muted" style="margin-top: 6px">
              工具 {{ item.tools }} · 思考 {{ item.thinking }} · 上下文 {{ item.context_window }}
            </p>
          </div>
        </div>
      </div>

      <div class="card">
        <h2>用量与成本</h2>
        <div v-if="!usage.length" class="empty" style="margin-top: 14px">还没有模型调用记录</div>
        <div v-else class="list" style="margin-top: 14px">
          <div v-for="(item, index) in usage" :key="index" class="list-item">
            <div class="row spread">
              <strong>{{ item.bucket }} · {{ item.task_type }}</strong>
              <span class="badge green">¥{{ item.cost_cny }}</span>
            </div>
            <p class="muted" style="margin-top: 6px">
              {{ item.provider }} / {{ item.model }} · {{ item.calls }} 次 · {{ item.prompt_tokens }}+{{ item.completion_tokens }} tokens
            </p>
          </div>
        </div>
      </div>

      <div class="card">
        <h2>最近调用</h2>
        <div v-if="!calls.length" class="empty" style="margin-top: 14px">暂无调用</div>
        <div v-else class="list" style="margin-top: 14px">
          <div v-for="item in calls" :key="item.id" class="list-item">
            <div class="row spread">
              <strong>{{ item.task_type }} · {{ item.status }}</strong>
              <span class="badge gray">{{ item.latency_ms }}ms</span>
            </div>
            <p class="muted" style="margin-top: 6px">
              {{ item.provider }} / {{ item.model }} · retry {{ item.retry_count }} · {{ item.request_id }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
