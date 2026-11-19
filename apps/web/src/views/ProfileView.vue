<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BookOpen, Check, Download, History, Pencil, Plus, Sparkles, Trash2, X } from 'lucide-vue-next'
import { api, ApiError } from '../api/client'
import { workspace } from '../stores/workspace'
import { friendlyError } from '../utils/friendly'
import type { ProfileClaim, ProfileDiff, ProfileSnapshot } from '../types'

const DIMENSIONS: Array<{ key: string; label: string; hint: string }> = [
  { key: 'identity_background', label: '身份与技术背景', hint: '你是谁、熟悉什么' },
  { key: 'cognitive_style', label: '思考方式', hint: '你通常怎么想问题' },
  { key: 'attention_trajectory', label: '关注方向', hint: '最近你更在意什么' },
  { key: 'high_frequency_pitfalls', label: '常见坑', hint: '容易反复遇到的坎' },
  { key: 'growth_signals', label: '成长信号', hint: '正在变好的地方' },
]

const route = useRoute()
const router = useRouter()

const current = ref<ProfileSnapshot | null>(null)
const snapshots = ref<ProfileSnapshot[]>([])
const diff = ref<ProfileDiff | null>(null)
const error = ref('')
const busy = ref(false)
const showHistory = ref(false)
const edit = ref<{ group: string; key: string; value: string; id?: number } | null>(null)

const groups = computed(() => {
  const result: Record<string, ProfileClaim[]> = {}
  for (const claim of current.value?.claims || []) {
    if (claim.is_deleted) continue
    ;(result[claim.group] ||= []).push(claim)
  }
  return result
})

const filledDimensions = computed(
  () => DIMENSIONS.filter((item) => (groups.value[item.key] || []).length > 0).length,
)

function indexLabel(index: number): string {
  return `第 ${snapshots.value.length - index} 次记录`
}

function message(err: unknown): string {
  return err instanceof ApiError ? friendlyError(err) : friendlyError(err)
}

async function load(): Promise<void> {
  snapshots.value = await api.get<ProfileSnapshot[]>('/profile/snapshots')
  try {
    current.value = await api.get<ProfileSnapshot>('/profile/current')
  } catch {
    current.value = null
  }
}
onMounted(async () => {
  await load()
  if (route.query.generate === '1') {
    await router.replace({ query: {} })
    await refresh()
  }
})

function nextPeriod(): string {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `p-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}-${Math.random().toString(36).slice(2, 5)}`
}

async function refresh(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    const model = workspace.state.model
    const fresh = await api.post<ProfileSnapshot>('/profile/generate', {
      period: nextPeriod(),
      provider: model.provider,
      model: model.model,
      credential_id: model.credentialId,
      ...(model.temporaryKey ? { temporary_api_key: model.temporaryKey } : {}),
    })
    if (fresh.status === 'FAILED') {
      error.value = '画像这次没能更新，稍后再试一次'
    } else {
      current.value = fresh
      await load()
    }
  } catch (err) {
    error.value = message(err)
  } finally {
    busy.value = false
  }
}

async function saveClaim(): Promise<void> {
  if (!edit.value) return
  const target = edit.value
  await api.put('/profile/claims', {
    group: target.group,
    key: target.key || '新的描述',
    value: target.value,
    evidence_fragment_ids: [],
  })
  edit.value = null
  await load()
}

async function removeClaim(claim: ProfileClaim): Promise<void> {
  await api.delete(`/profile/claims/${claim.id}`)
  await load()
}

async function exportProfile(): Promise<void> {
  if (!current.value) return
  const markdown = await api.getText(
    `/profile/snapshot/export?period=${encodeURIComponent(current.value.period)}`,
  )
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = '我的成长画像.md'
  link.click()
  URL.revokeObjectURL(link.href)
}

async function loadDiff(index: number): Promise<void> {
  const to = snapshots.value[index]
  const from = snapshots.value[index + 1]
  if (!to || !from) {
    diff.value = null
    return
  }
  diff.value = await api.get<ProfileDiff>(
    `/profile/diff?from_period=${encodeURIComponent(from.period)}&to_period=${encodeURIComponent(to.period)}`,
  )
}
</script>

<template>
  <div class="profile-view relative min-h-full">
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="absolute -left-20 top-10 h-72 w-72 rounded-full bg-brand-teal/10 blur-3xl animate-float"></div>
      <div class="absolute -right-20 top-52 h-72 w-72 rounded-full bg-brand/10 blur-3xl animate-float" style="animation-delay: -3s"></div>
    </div>

    <div class="relative mx-auto w-full max-w-[900px] px-5 pb-24 pt-12">
      <div class="mb-8 flex flex-wrap items-end justify-between gap-4 animate-fade-up">
        <div>
          <div class="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-brand to-brand-teal text-white shadow-glow">
            <BookOpen :size="22" />
          </div>
          <h1 class="text-[30px] font-semibold tracking-tight text-ink">我的成长画像</h1>
          <p class="mt-2 text-[14px] text-[#7a839a]">
            {{ current ? `已经记下 ${filledDimensions} 个方面，共 ${current.claims.filter((c) => !c.is_deleted).length} 条描述` : '还没有画像，先让对话帮你画一张' }}
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="btn small" :disabled="busy" @click="refresh">
            <Sparkles :size="14" class="mr-1 inline" /> {{ busy ? '整理中…' : '更新画像' }}
          </button>
          <button v-if="current" type="button" class="btn ghost small" @click="exportProfile">
            <Download :size="14" class="mr-1 inline" /> 导出画像记录
          </button>
          <button type="button" class="btn ghost small" @click="showHistory = !showHistory">
            <History :size="14" class="mr-1 inline" /> 上几次变化
          </button>
        </div>
      </div>

      <p v-if="error" class="mb-5 rounded-[14px] border border-red-100 bg-red-50 px-4 py-3 text-[13px] text-[#b42318]">{{ error }}</p>

      <div v-if="!current" class="rounded-[20px] border border-dashed border-[#dfe3ee] bg-white/70 px-6 py-16 text-center shadow-soft">
        <Sparkles :size="28" class="mx-auto mb-3 text-brand/60" />
        <p class="text-[15px] font-medium text-ink">还没有画像记录</p>
        <p class="mt-1.5 text-[13px] text-[#8b93a7]">回到对话页上传几份对话，或点上面的「更新画像」</p>
      </div>

      <div v-else class="space-y-4">
        <section
          v-for="dimension in DIMENSIONS"
          :key="dimension.key"
          class="rounded-[20px] border border-white/80 bg-white/85 p-6 shadow-soft backdrop-blur-sm"
        >
          <div class="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 class="text-[17px] font-semibold text-ink">{{ dimension.label }}</h2>
              <p class="mt-1 text-[12px] text-[#9aa2b4]">{{ dimension.hint }}</p>
            </div>
            <button
              type="button"
              class="flex h-8 w-8 items-center justify-center rounded-lg text-[#9aa2b4] transition-colors hover:bg-brand/10 hover:text-brand"
              aria-label="补充一条"
              @click="edit = { group: dimension.key, key: '', value: '' }"
            >
              <Plus :size="16" />
            </button>
          </div>

          <div v-if="(groups[dimension.key] || []).length" class="space-y-2">
            <div
              v-for="claim in groups[dimension.key]"
              :key="claim.id"
              class="group flex items-start gap-3 rounded-[13px] bg-[#f8fafc] px-4 py-3"
            >
              <span class="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-gradient-to-br from-brand to-brand-teal"></span>
              <div class="min-w-0 flex-1">
                <p class="text-[14px] leading-relaxed text-[#434c60]">{{ claim.value }}</p>
                <p v-if="claim.user_corrected" class="mt-1 flex items-center gap-1 text-[11px] text-[#0f766e]">
                  <Check :size="11" /> 你调整过的
                </p>
              </div>
              <div class="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                <button type="button" class="flex h-7 w-7 items-center justify-center rounded-lg text-[#9aa2b4] hover:bg-white hover:text-brand" aria-label="调整描述" @click="edit = { group: claim.group, key: claim.key, value: claim.value, id: claim.id }">
                  <Pencil :size="14" />
                </button>
                <button type="button" class="flex h-7 w-7 items-center justify-center rounded-lg text-[#9aa2b4] hover:bg-red-50 hover:text-[#b42318]" aria-label="不再保留" @click="removeClaim(claim)">
                  <Trash2 :size="14" />
                </button>
              </div>
            </div>
          </div>
          <p v-else class="rounded-[12px] border border-dashed border-[#e4e8f0] px-4 py-5 text-center text-[12px] text-[#a3abbb]">
            这一块还空着，点右上角补一条
          </p>

          <div v-if="edit && edit.group === dimension.key" class="mt-4 space-y-3 rounded-[14px] bg-brand/5 p-4 animate-fade-up">
            <input v-model="edit.key" class="text-[13px]" placeholder="这条大概叫什么（可留空）" />
            <textarea v-model="edit.value" class="min-h-[80px] text-[13px]" placeholder="用你自己的话写下来"></textarea>
            <div class="flex gap-2">
              <button type="button" class="btn small" @click="saveClaim">保存这一条</button>
              <button type="button" class="btn ghost small" @click="edit = null"><X :size="13" class="mr-1 inline" />取消</button>
            </div>
          </div>
        </section>

        <section v-if="showHistory" class="rounded-[20px] border border-white/80 bg-white/85 p-6 shadow-soft backdrop-blur-sm animate-fade-up">
          <h2 class="mb-4 text-[17px] font-semibold text-ink">上几次变化</h2>
          <div class="space-y-2">
            <button
              v-for="(item, index) in snapshots"
              :key="item.id"
              type="button"
              class="flex w-full items-center justify-between rounded-[12px] border border-[#eef0f6] px-4 py-3 text-left transition-colors hover:bg-[#f8fafc]"
              @click="loadDiff(index)"
            >
              <span class="text-[13px] font-medium text-[#434c60]">{{ indexLabel(index) }}</span>
              <span class="text-[12px] text-[#9aa2b4]">{{ item.claims.filter((c) => !c.is_deleted).length }} 条描述</span>
            </button>
          </div>
          <div v-if="diff" class="mt-4 rounded-[14px] bg-[#f8fafc] p-4">
            <p class="text-[13px] font-medium text-[#434c60]">
              这次新增 {{ diff.added.length }} 条，少了 {{ diff.removed.length }} 条，改了 {{ diff.changed.length }} 条
            </p>
            <ul v-if="diff.added.length" class="mt-3 space-y-1.5">
              <li v-for="claim in diff.added.slice(0, 6)" :key="claim.id" class="text-[12px] text-[#5b6478]">· {{ claim.value }}</li>
            </ul>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
