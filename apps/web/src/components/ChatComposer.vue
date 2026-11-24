<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUp, Sparkles, X } from 'lucide-vue-next'
import FileDropzone from './FileDropzone.vue'
import DirectionPicker from './DirectionPicker.vue'
import { workspace } from '../stores/workspace'

const input = computed({
  get: () => workspace.state.input,
  set: (value: string) => (workspace.state.input = value),
})
const focused = ref(false)

function send(): void {
  workspace.send()
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    send()
  }
}
</script>

<template>
  <div
    class="composer group relative z-50 rounded-[24px] bg-white/90 border transition-all duration-200"
    :class="focused ? 'border-brand/50 shadow-glow' : 'border-white/80 shadow-soft'"
  >
    <div class="border-b border-[#eef0f6] px-5 pb-3 pt-4">
      <DirectionPicker />
    </div>
    <div v-if="workspace.selectedPrompts.value.length" class="flex flex-wrap items-center gap-1.5 px-5 pt-3 animate-fade-up">
      <span class="text-[10px] text-[#a3abbb]">已带提示词</span>
      <span
        v-for="prompt in workspace.selectedPrompts.value"
        :key="prompt.id"
        class="inline-flex items-center gap-1 rounded-full bg-brand/5 px-2.5 py-1 text-[11px] font-semibold text-brand"
        :title="prompt.text"
      >
        {{ prompt.label }}
        <button
          type="button"
          class="flex h-3.5 w-3.5 items-center justify-center rounded-full hover:bg-brand/10"
          :aria-label="`移除 ${prompt.label}`"
          @click="workspace.togglePrompt(prompt.id)"
        >
          <X :size="10" />
        </button>
      </span>
    </div>
    <div class="flex items-start gap-3 px-5 pt-3">
      <div class="mt-1.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-brand-teal text-white">
        <Sparkles :size="16" />
      </div>
      <textarea
        v-model="input"
        rows="2"
        class="max-h-48 min-h-[56px] w-full resize-none border-0 bg-transparent py-1.5 text-[15px] leading-relaxed text-ink outline-none placeholder:text-[#9aa2b4] focus:outline-none focus:ring-0"
        placeholder="说说你想整理什么，比如「帮我复盘这一周」"
        @focus="focused = true"
        @blur="focused = false"
        @keydown="onKeydown"
      />
    </div>
    <div class="flex items-center justify-between px-4 pb-3 pt-1">
      <div class="flex items-center gap-3 pl-1">
        <FileDropzone />
        <span class="text-[12px] text-[#9aa2b4]">回车发送 · Shift 换行</span>
      </div>
      <button
        type="button"
        class="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand to-brand-light text-white shadow-glow transition-all duration-200 hover:scale-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
        :disabled="workspace.state.busy || (!input.trim() && workspace.state.files.length === 0)"
        aria-label="发送"
        @click="send"
      >
        <ArrowUp :size="18" />
      </button>
    </div>
  </div>
</template>
