<script setup lang="ts">
import { ref } from 'vue'
import { Paperclip } from 'lucide-vue-next'
import { workspace } from '../stores/workspace'

const inputRef = ref<HTMLInputElement | null>(null)
const dragging = ref(false)

function pick(): void {
  inputRef.value?.click()
}

function onFiles(event: Event): void {
  const target = event.target as HTMLInputElement
  if (target.files?.length) workspace.addFiles(Array.from(target.files))
  target.value = ''
}

function onDrop(event: DragEvent): void {
  dragging.value = false
  if (event.dataTransfer?.files?.length) workspace.addFiles(Array.from(event.dataTransfer.files))
}
</script>

<template>
  <div class="relative inline-flex">
    <input ref="inputRef" type="file" multiple accept=".md,.markdown,.txt,.zip" class="hidden" @change="onFiles" />
    <button
      type="button"
      class="flex h-9 w-9 items-center justify-center rounded-full border transition-all duration-200"
      :class="dragging
        ? 'scale-105 border-brand bg-brand text-white shadow-glow'
        : 'border-[#e4e8f0] bg-white/80 text-[#7a839a] hover:border-brand/50 hover:bg-brand/5 hover:text-brand'"
      title="添加对话文件"
      aria-label="添加对话文件"
      @click="pick"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <Paperclip :size="17" />
    </button>
    <span
      v-if="workspace.state.files.length"
      class="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-gradient-to-br from-brand to-brand-teal px-1 text-[10px] font-semibold text-white shadow-sm"
    >
      {{ workspace.state.files.length }}
    </span>
  </div>
</template>
