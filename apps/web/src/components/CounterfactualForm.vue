<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { LoaderCircle, Plus, Trash2 } from 'lucide-vue-next'
import { samplesApi } from '../api/client'
import type { CounterfactualEntry } from '../types'
import { friendlyError } from '../utils/friendly'

const PROMPTS = [
  { value: 'to_ai', label: '没对 AI 说出口的', hint: '当时想说却没输入的话' },
  { value: 'to_person', label: '换个对象会怎么说', hint: '如果对方是朋友或同事' },
  { value: 'real_goal', label: '当时真正想做的', hint: '表面问题背后的真实目标' },
]

const entries = ref<CounterfactualEntry[]>([])
const promptType = ref('to_ai')
const content = ref('')
const sourceLabel = ref('')
const busy = ref(false)
const loading = ref(false)
const error = ref('')

const currentHint = () => PROMPTS.find((item) => item.value === promptType.value)?.hint || ''

async function load(): Promise<void> {
  loading.value = true
  try {
    entries.value = await samplesApi.listCounterfactuals()
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    loading.value = false
  }
}

async function add(): Promise<void> {
  if (!content.value.trim()) return
  busy.value = true
  error.value = ''
  try {
    await samplesApi.addCounterfactual({
      prompt_type: promptType.value,
      content: content.value.trim(),
      source_label: sourceLabel.value.trim() || undefined,
    })
    content.value = ''
    sourceLabel.value = ''
    await load()
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busy.value = false
  }
}

async function remove(entryId: number): Promise<void> {
  error.value = ''
  try {
    await samplesApi.deleteCounterfactual(entryId)
    await load()
  } catch (err) {
    error.value = friendlyError(err)
  }
}

onMounted(load)
</script>

<template>
  <section class="card animate-fade-up">
    <div class="card-head">
      <div>
        <h2 class="text-[16px] font-semibold text-ink">反事实补录</h2>
        <p class="mt-1 text-[12px] text-muted">把没说出口的话补进来，画像才不会只反映你对 AI 的那一面。</p>
      </div>
      <span class="badge blue">{{ entries.length }} 条</span>
    </div>

    <div v-if="error" class="mb-4 rounded-[12px] border border-red-100 bg-red-50 px-4 py-2.5 text-[12px] text-[#b42318]">
      {{ error }}
    </div>

    <div class="flex flex-wrap gap-2">
      <button
        v-for="item in PROMPTS"
        :key="item.value"
        type="button"
        class="rounded-full px-3 py-1.5 text-[12px] font-medium transition-all"
        :class="promptType === item.value
          ? 'bg-brand text-white shadow-sm'
          : 'bg-[#f1f3fa] text-[#667085] hover:bg-[#e8ebf5]'"
        @click="promptType = item.value"
      >
        {{ item.label }}
      </button>
    </div>
    <p class="mt-2 text-[12px] text-muted">{{ currentHint() }}</p>

    <div class="mt-4 space-y-3">
      <textarea
        v-model="content"
        rows="4"
        class="w-full resize-none"
        placeholder="比如：其实我更想问的是，这个方向到底值不值得继续投入…"
      />
      <div class="flex flex-col gap-3 sm:flex-row">
        <input
          v-model="sourceLabel"
          class="flex-1"
          placeholder="这条更像对谁说的？（可选，如：导师 / 同事）"
        />
        <button type="button" class="btn" :disabled="busy || !content.trim()" @click="add">
          <LoaderCircle v-if="busy" :size="15" class="animate-spin" />
          <Plus v-else :size="15" />
          记下来
        </button>
      </div>
    </div>

    <div class="mt-6">
      <h3 class="text-[13px] font-semibold text-ink">已经补录的</h3>
      <div v-if="loading" class="mt-3 flex items-center gap-2 text-[12px] text-muted">
        <LoaderCircle :size="14" class="animate-spin text-brand" /> 读取中…
      </div>
      <div v-else-if="entries.length" class="list mt-3">
        <div v-for="item in entries" :key="item.id" class="list-item flex items-start gap-3">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="badge gray">{{ item.prompt_type }}</span>
              <span v-if="item.source_label" class="text-[11px] text-muted">{{ item.source_label }}</span>
            </div>
            <p class="mt-1.5 whitespace-pre-wrap text-[13px] leading-relaxed text-ink">{{ item.content }}</p>
          </div>
          <button
            type="button"
            class="shrink-0 rounded-lg p-1.5 text-[#9aa2b4] transition-colors hover:bg-red-50 hover:text-[#b42318]"
            aria-label="删除补录"
            @click="remove(item.id)"
          >
            <Trash2 :size="15" />
          </button>
        </div>
      </div>
      <div v-else class="empty mt-3">还没有补录，写下第一条吧。</div>
    </div>
  </section>
</template>
