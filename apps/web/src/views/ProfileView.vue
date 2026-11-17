<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '../api/client'
import type { ProfileClaim, ProfileDiff, ProfileSnapshot } from '../types'

const groupLabels: Record<string, string> = {
  identity_background: '身份与技术背景',
  cognitive_style: '认知风格',
  attention_trajectory: '注意力轨迹',
  high_frequency_pitfalls: '高频坑',
  growth_signals: '成长信号',
}

const period = ref('')
const provider = ref('deepseek')
const current = ref<ProfileSnapshot | null>(null)
const snapshots = ref<ProfileSnapshot[]>([])
const diff = ref<ProfileDiff | null>(null)
const fromPeriod = ref('')
const toPeriod = ref('')
const error = ref('')
const busy = ref(false)
const edit = ref<{ group: string; key: string; value: string } | null>(null)

const groups = computed(() => {
  const result: Record<string, ProfileClaim[]> = {}
  for (const claim of current.value?.claims || []) {
    ;(result[claim.group] ||= []).push(claim)
  }
  return result
})

function message(err: unknown): string {
  return err instanceof ApiError ? err.body?.message || err.message : '操作失败'
}

async function load(): Promise<void> {
  snapshots.value = await api.get<ProfileSnapshot[]>('/profile/snapshots')
  try {
    current.value = await api.get<ProfileSnapshot>('/profile/current')
  } catch {
    current.value = null
  }
}
onMounted(load)

async function generate(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    await api.post<ProfileSnapshot>('/profile/generate', {
      period: period.value,
      provider: provider.value,
    })
    await load()
  } catch (err) {
    error.value = message(err)
  } finally {
    busy.value = false
  }
}

async function saveClaim(): Promise<void> {
  if (!edit.value) return
  await api.put('/profile/claims', {
    group: edit.value.group,
    key: edit.value.key,
    value: edit.value.value,
    evidence_fragment_ids: [],
  })
  edit.value = null
  await load()
}

async function removeClaim(claim: ProfileClaim): Promise<void> {
  await api.delete(`/profile/claims/${claim.id}`)
  await load()
}

async function exportSnapshot(): Promise<void> {
  if (!current.value) return
  const markdown = await api.getText(
    `/profile/snapshot/export?period=${encodeURIComponent(current.value.period)}`,
  )
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `cairn-profile-${current.value.period}.md`
  link.click()
  URL.revokeObjectURL(link.href)
}

async function loadDiff(): Promise<void> {
  if (!fromPeriod.value || !toPeriod.value) return
  diff.value = await api.get<ProfileDiff>(
    `/profile/diff?from_period=${encodeURIComponent(fromPeriod.value)}&to_period=${encodeURIComponent(toPeriod.value)}`,
  )
}
</script>

<template>
  <div class="grid two">
    <div>
      <div class="card">
        <div class="card-head">
          <div>
            <h2>生成画像快照</h2>
            <p>每条结论必须带证据；用户修正会原样继承。</p>
          </div>
          <span class="badge blue">增量更新</span>
        </div>
        <div class="row">
          <input v-model="period" placeholder="2026-W47" style="flex: 1" />
          <select v-model="provider" style="width: 150px">
            <option value="deepseek">DeepSeek</option>
            <option value="volcengine">火山引擎</option>
            <option value="hunyuan">混元</option>
            <option value="openai_compat">兼容端点</option>
          </select>
          <button class="btn" :disabled="busy" @click="generate">生成</button>
        </div>
        <p v-if="error" class="error">{{ error }}</p>
      </div>

      <div v-if="current" class="card">
        <div class="card-head">
          <div>
            <h2>当前画像 · {{ current.period }}</h2>
            <p>{{ current.prompt_version }} · {{ current.claims.length }} 条结论</p>
          </div>
          <div class="row">
            <button class="btn ghost small" @click="exportSnapshot">导出 MD</button>
            <button class="btn soft small" @click="edit = { group: 'cognitive_style', key: '', value: '' }">
              新增结论
            </button>
          </div>
        </div>

        <div v-if="edit" class="card" style="box-shadow: none; background: #f8fafc">
          <div class="field">
            <label>分组</label>
            <select v-model="edit.group">
              <option v-for="(label, key) in groupLabels" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div class="field">
            <label>键</label>
            <input v-model="edit.key" />
          </div>
          <div class="field">
            <label>结论</label>
            <textarea v-model="edit.value" style="min-height: 80px"></textarea>
          </div>
          <div class="row">
            <button class="btn small" @click="saveClaim">保存</button>
            <button class="btn ghost small" @click="edit = null">取消</button>
          </div>
        </div>

        <div v-for="(claims, key) in groups" :key="key" style="margin-top: 20px">
          <h3 style="font-size: 13px; color: var(--muted); margin-bottom: 10px">
            {{ groupLabels[key] || key }}
          </h3>
          <div class="list">
            <div v-for="claim in claims" :key="claim.id" class="list-item">
              <div class="row spread">
                <strong>{{ claim.key }}</strong>
                <span class="badge" :class="claim.user_corrected ? 'amber' : 'gray'">
                  {{ claim.user_corrected ? '用户修正' : claim.source }}
                </span>
              </div>
              <p style="margin-top: 6px">{{ claim.value }}</p>
              <div class="evidence">
                <span v-for="id in claim.evidence_fragment_ids" :key="id">#{{ id }}</span>
                <span v-if="!claim.evidence_fragment_ids.length">用户手工添加</span>
              </div>
              <div class="row" style="margin-top: 10px">
                <button class="btn ghost small" @click="edit = { group: claim.group, key: claim.key, value: claim.value }">编辑</button>
                <button class="btn danger small" @click="removeClaim(claim)">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="card empty">还没有画像，先生成一份。</div>
    </div>

    <div>
      <div class="card">
        <div class="card-head">
          <div>
            <h2>历史快照与 Diff</h2>
            <p>任意两个周期都能比较变化。</p>
          </div>
        </div>
        <div class="row">
          <select v-model="fromPeriod" style="flex: 1">
            <option value="">起始周期</option>
            <option v-for="item in snapshots" :key="item.id" :value="item.period">{{ item.period }}</option>
          </select>
          <select v-model="toPeriod" style="flex: 1">
            <option value="">结束周期</option>
            <option v-for="item in snapshots" :key="item.id" :value="item.period">{{ item.period }}</option>
          </select>
          <button class="btn ghost small" @click="loadDiff">比较</button>
        </div>

        <div v-if="diff" class="list" style="margin-top: 18px">
          <div class="list-item">
            <strong>新增 {{ diff.added.length }} · 移除 {{ diff.removed.length }} · 变化 {{ diff.changed.length }}</strong>
          </div>
          <div v-for="(item, index) in diff.changed" :key="index" class="list-item">
            <p><strong>{{ item.key }}</strong></p>
            <p class="muted">{{ item.from }} → {{ item.to }}</p>
          </div>
        </div>

        <div class="list" style="margin-top: 18px">
          <div v-for="item in snapshots" :key="item.id" class="list-item">
            <div class="row spread">
              <strong>{{ item.period }}</strong>
              <span class="badge" :class="item.status === 'DONE' ? 'green' : 'red'">{{ item.status }}</span>
            </div>
            <p class="muted" style="margin-top: 6px">{{ item.claims.length }} 条 · {{ item.model || '-' }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
