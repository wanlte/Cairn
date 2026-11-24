<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Check, ChevronDown, Plus, Sparkles, Trash2, X } from 'lucide-vue-next'
import { workspace } from '../stores/workspace'
import { DIRECTION_LABELS, DIRECTION_OPTIONS } from '../utils/direction'
import type { DirectionKey } from '../types'

const open = ref(false)
const root = ref<HTMLElement | null>(null)
const newLabel = ref('')
const newText = ref('')

const sortedPrompts = computed(() => {
  const current = workspace.state.direction
  return [...workspace.availablePrompts.value].sort(
    (a, b) => Number(b.direction === current) - Number(a.direction === current),
  )
})

const selectedPrompts = workspace.selectedPrompts
const currentDirection = computed(() => workspace.state.direction)

function isSelected(id: string): boolean {
  return workspace.state.selectedPromptIds.includes(id)
}

function saveCustom(): void {
  if (!newLabel.value.trim() || !newText.value.trim()) return
  workspace.addPrompt(newLabel.value, newText.value, workspace.state.direction)
  newLabel.value = ''
  newText.value = ''
  open.value = false
}

function selectPrompt(id: string): void {
  workspace.togglePrompt(id)
  open.value = false
}

function onDocumentClick(event: MouseEvent): void {
  if (open.value && root.value && !root.value.contains(event.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => document.removeEventListener('click', onDocumentClick))

function choose(key: DirectionKey): void {
  // 再点一次已选方向就取消，回到自由提问（方向完全可选）
  workspace.setDirection(workspace.state.direction === key ? 'free' : key)
}

const chipText = computed(() => {
  const parts: string[] = []
  if (currentDirection.value !== 'free') parts.push(DIRECTION_LABELS[currentDirection.value])
  else parts.push('不设方向')
  if (selectedPrompts.value.length) parts.push(`提示词 ${selectedPrompts.value.length}`)
  return parts.join(' · ')
})
</script>

<template>
  <div ref="root" class="relative">
    <button
      type="button"
      class="flex max-w-full items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-medium transition-all duration-200"
      :class="open
        ? 'border-brand/40 bg-brand/5 text-brand'
        : 'border-[#e4e8f0] bg-white/80 text-[#5b6478] hover:border-brand/30 hover:text-brand'"
      @click="open = !open"
    >
      <Sparkles :size="12" />
      <span class="truncate">{{ chipText }}</span>
      <ChevronDown :size="12" :class="open ? 'rotate-180 transition-transform' : 'transition-transform'" />
    </button>

    <p v-if="workspace.state.recommendReason" class="mt-1.5 text-[10px] leading-relaxed text-[#a3abbb]">
      {{ workspace.state.recommendReason }}
    </p>

    <div
      v-if="open"
      class="absolute bottom-full left-0 z-50 mb-2 max-h-[420px] w-[min(92vw,380px)] overflow-y-auto rounded-[16px] border border-[#e4e8f0] bg-white p-3 shadow-xl animate-fade-up"
    >
      <div class="mb-2 flex items-center justify-between">
        <p class="text-[12px] font-semibold text-ink">方向与提示词 · 都是可选的</p>
        <button
          type="button"
          class="flex h-6 w-6 items-center justify-center rounded-lg text-[#9aa2b4] hover:bg-[#f4f6fb]"
          aria-label="收起"
          @click="open = false"
        >
          <X :size="14" />
        </button>
      </div>

      <p class="mb-1.5 text-[11px] font-semibold text-[#9aa2b4]">方向</p>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="option in DIRECTION_OPTIONS"
          :key="option.key"
          type="button"
          class="rounded-full px-2.5 py-1 text-[11px] font-medium transition-all duration-200"
          :class="currentDirection === option.key && !workspace.state.customDirection
            ? 'bg-brand text-white shadow-sm'
            : 'bg-[#f4f6fb] text-[#6b7488] hover:bg-brand/10 hover:text-brand'"
          @click="choose(option.key)"
        >
          {{ option.label }}
        </button>
      </div>
      <p class="mt-1.5 text-[10px] text-[#a3abbb]">不选也没关系，我会自己判断该怎么做。</p>

      <div class="my-3 border-t border-[#eef0f6]" />

      <p class="mb-1.5 text-[11px] font-semibold text-[#9aa2b4]">常用提示词 · 点击选用</p>
      <div class="space-y-1.5">
        <div
          v-for="prompt in sortedPrompts"
          :key="prompt.id"
          class="flex items-start gap-2 rounded-[11px] border px-2.5 py-2 transition-colors"
          :class="isSelected(prompt.id)
            ? 'border-brand/30 bg-brand/5'
            : 'border-[#eef0f6] hover:border-brand/25 hover:bg-[#fafbff]'"
        >
          <button type="button" class="flex min-w-0 flex-1 items-start gap-2 text-left" @click="selectPrompt(prompt.id)">
            <span
              class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border"
              :class="isSelected(prompt.id) ? 'border-brand bg-brand text-white' : 'border-[#cfd5e2]'"
            >
              <Check v-if="isSelected(prompt.id)" :size="10" />
            </span>
            <span class="min-w-0">
              <span class="flex flex-wrap items-center gap-1.5">
                <span class="text-[12px] font-semibold text-ink">{{ prompt.label }}</span>
                <span class="rounded-full bg-[#f1f4f9] px-1.5 py-0.5 text-[9px] text-[#8b93a7]">
                  {{ DIRECTION_LABELS[prompt.direction] }}
                </span>
                <span v-if="prompt.custom" class="rounded-full bg-brand-teal/10 px-1.5 py-0.5 text-[9px] text-[#0f766e]">长期保存</span>
              </span>
              <span class="mt-0.5 block text-[11px] leading-relaxed text-[#7a839a]">{{ prompt.text }}</span>
            </span>
          </button>
          <button
            v-if="prompt.custom"
            type="button"
            class="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-[#b0b6c4] hover:bg-red-50 hover:text-[#b42318]"
            aria-label="删除这条提示词"
            @click="workspace.removePrompt(prompt.id)"
          >
            <Trash2 :size="12" />
          </button>
        </div>
      </div>

      <div class="mt-3 space-y-2 border-t border-[#eef0f6] pt-3">
        <p class="text-[11px] font-semibold text-[#5b6478]">定义自己的提示词 · 长期保存</p>
        <input v-model="newLabel" class="!py-1.5 text-[12px]" placeholder="起个名字，比如「先列风险」" />
        <textarea
          v-model="newText"
          rows="2"
          class="min-h-0 !py-1.5 text-[12px]"
          placeholder="写清楚想让我做什么，比如：先找出没有证据支撑的判断"
        ></textarea>
        <div class="flex items-center justify-between gap-2">
          <input
            v-model="workspace.state.customDirection"
            class="min-w-0 flex-1 !py-1.5 text-[11px]"
            placeholder="本次临时补充（不保存）"
          />
          <button
            type="button"
            class="flex shrink-0 items-center gap-1 rounded-full bg-brand px-3 py-1.5 text-[11px] font-semibold text-white disabled:opacity-40"
            :disabled="!newLabel.trim() || !newText.trim()"
            @click="saveCustom"
          >
            <Plus :size="12" /> 保存并选用
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
