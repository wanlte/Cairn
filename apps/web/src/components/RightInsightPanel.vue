<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Compass, LoaderCircle, RotateCw, Sparkles } from 'lucide-vue-next'
import { api } from '../api/client'
import { workspace } from '../stores/workspace'
import { DIRECTION_LABELS } from '../utils/direction'
import type { ProfileClaim, ProfileSnapshot } from '../types'

const router = useRouter()
const snapshot = ref<ProfileSnapshot | null>(null)
const loading = ref(false)
const failed = ref(false)

const GROUPS: Array<{ key: string; label: string }> = [
  { key: 'identity_background', label: '身份背景' },
  { key: 'cognitive_style', label: '思考方式' },
  { key: 'attention_trajectory', label: '关注方向' },
  { key: 'high_frequency_pitfalls', label: '常见坑' },
  { key: 'growth_signals', label: '成长信号' },
]

const claimsByGroup = computed(() => {
  const grouped = new Map<string, ProfileClaim[]>()
  for (const claim of snapshot.value?.claims || []) {
    if (claim.is_deleted || !claim.value?.trim()) continue
    const list = grouped.get(claim.group) || []
    list.push(claim)
    grouped.set(claim.group, list)
  }
  return grouped
})

const filledCount = computed(() => claimsByGroup.value.size)
const totalCount = computed(() =>
  [...claimsByGroup.value.values()].reduce((sum, list) => sum + list.length, 0),
)

const directionLabel = computed(() => DIRECTION_LABELS[workspace.state.direction])

async function loadProfile(): Promise<void> {
  loading.value = true
  failed.value = false
  try {
    snapshot.value = await api.get<ProfileSnapshot>('/profile/current')
  } catch (error) {
    console.error('加载画像速览失败', error)
    snapshot.value = null
    failed.value = true
  } finally {
    loading.value = false
  }
}

function openProfile(): void {
  void router.push({ name: 'profile' })
}

onMounted(() => {
  void loadProfile()
})

watch(
  () => workspace.state.stage,
  (stage, previous) => {
    if (stage === previous) return
    if (stage === '已完成' || (previous === '处理中' && stage !== '处理中')) void loadProfile()
  },
)
</script>

<template>
  <aside class="insight-panel">
    <div class="rounded-[18px] border border-white/80 bg-white/85 p-4 shadow-soft backdrop-blur-xl">
      <div class="flex items-center gap-2">
        <span class="flex h-7 w-7 items-center justify-center rounded-[10px] bg-brand/10 text-brand">
          <Compass :size="15" />
        </span>
        <p class="text-[13px] font-semibold text-ink">这次怎么聊</p>
      </div>
      <div class="mt-3 space-y-2 text-[12px] leading-relaxed">
        <div class="flex items-center justify-between gap-2 rounded-xl bg-[#f8fafc] px-3 py-2">
          <span class="text-muted">当前方向</span>
          <span class="font-medium text-ink">{{ directionLabel }}</span>
        </div>
        <p v-if="workspace.state.recommendReason" class="rounded-xl border border-brand/10 bg-brand/5 px-3 py-2 text-[#5b6478]">
          {{ workspace.state.recommendReason }}
        </p>
        <p v-else class="rounded-xl bg-[#f8fafc] px-3 py-2 text-muted">
          直接说你想聊什么，系统会自动判断要不要复盘。
        </p>
      </div>
    </div>

    <div class="mt-3 rounded-[18px] border border-white/80 bg-white/85 p-4 shadow-soft backdrop-blur-xl">
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <span class="flex h-7 w-7 items-center justify-center rounded-[10px] bg-brand-teal/10 text-[#0f766e]">
            <Sparkles :size="15" />
          </span>
          <p class="text-[13px] font-semibold text-ink">画像速览</p>
        </div>
        <button
          type="button"
          class="icon-btn"
          aria-label="刷新画像速览"
          :disabled="loading"
          @click="loadProfile"
        >
          <LoaderCircle v-if="loading" :size="14" class="animate-spin" />
          <RotateCw v-else :size="14" />
        </button>
      </div>

      <div v-if="failed" class="mt-3 rounded-xl bg-[#fff9ee] px-3 py-3 text-[12px] leading-relaxed text-[#7a4a12]">
        画像暂时读不到，不影响继续聊天。
        <button type="button" class="font-semibold underline" @click="loadProfile">再试一次</button>
      </div>
      <div v-else-if="!snapshot" class="mt-3 rounded-xl border border-dashed border-[#dfe3ee] px-3 py-5 text-center text-[12px] leading-relaxed text-muted">
        还没有画像。聊几句或说一句「记住我是…」，这里就会出现你的成长记录。
      </div>
      <template v-else>
        <p class="mt-2.5 text-[11px] text-muted">已记下 {{ filledCount }} 个方面 · {{ totalCount }} 条描述</p>
        <div class="mt-3 space-y-3">
          <div v-for="group in GROUPS" :key="group.key">
            <div v-if="claimsByGroup.get(group.key)?.length" class="rounded-xl bg-[#f8fafc] px-3 py-2.5">
              <p class="text-[11px] font-semibold text-brand">{{ group.label }}</p>
              <p class="mt-1 line-clamp-2 text-[12px] leading-relaxed text-[#5b6478]">
                {{ claimsByGroup.get(group.key)![0]!.value }}
              </p>
              <p v-if="(claimsByGroup.get(group.key)?.length || 0) > 1" class="mt-1 text-[10px] text-muted">
                还有 {{ (claimsByGroup.get(group.key)?.length || 0) - 1 }} 条
              </p>
            </div>
          </div>
        </div>
      </template>

      <button type="button" class="mt-4 flex w-full items-center justify-center gap-1.5 rounded-xl border border-brand/15 bg-brand/5 py-2 text-[12px] font-semibold text-brand transition hover:bg-brand/10" @click="openProfile">
        查看完整画像 <ArrowRight :size="13" />
      </button>
    </div>
  </aside>
</template>

<style scoped>
.insight-panel { display: flex; flex-direction: column; min-height: 0; overflow-y: auto; padding-bottom: 8px; }
.icon-btn {
  display: flex; height: 24px; width: 24px; align-items: center; justify-content: center;
  border-radius: 8px; color: #9aa2b4; transition: background .15s, color .15s;
}
.icon-btn:hover:not(:disabled) { background: #f4f6fa; color: #172033; }
.icon-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
