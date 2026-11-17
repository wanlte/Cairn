<script setup lang="ts">
import { ref } from 'vue'
import { CheckCircle2, FileText, LoaderCircle, Trash2, UploadCloud, AlertCircle } from 'lucide-vue-next'
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

function sizeText(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <div>
    <input ref="inputRef" type="file" multiple accept=".md,.markdown,.txt,.zip" class="hidden" @change="onFiles" />
    <button
      type="button"
      class="group flex w-full items-center justify-center gap-3 rounded-[18px] border-2 border-dashed px-5 py-5 text-left transition-all duration-200"
      :class="dragging ? 'border-brand bg-brand/5 scale-[1.01]' : 'border-[#dfe3ee] bg-white/60 hover:border-brand/60 hover:bg-brand/[0.03]'"
      @click="pick"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-brand/10 text-brand transition-transform duration-200 group-hover:-translate-y-0.5">
        <UploadCloud :size="20" />
      </div>
      <div>
        <p class="text-[14px] font-semibold text-ink">把对话文件拖到这里，或点这里选择</p>
        <p class="mt-0.5 text-[12px] text-[#8b93a7]">支持 Markdown、TXT、ZIP，可以一次带上好几份</p>
      </div>
    </button>

    <div v-if="workspace.state.files.length" class="mt-3 space-y-2">
      <div
        v-for="file in workspace.state.files"
        :key="file.uid"
        class="flex items-center gap-3 rounded-[14px] border border-white/80 bg-white/80 px-4 py-2.5 shadow-sm"
      >
        <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
          :class="file.error ? 'bg-red-50 text-[#b42318]' : 'bg-brand/10 text-brand'">
          <AlertCircle v-if="file.error" :size="17" />
          <FileText v-else :size="17" />
        </div>
        <div class="min-w-0 flex-1">
          <p class="truncate text-[13px] font-medium text-ink">{{ file.name }}</p>
          <p class="mt-0.5 flex items-center gap-1.5 text-[11px] text-[#8b93a7]">
            <LoaderCircle v-if="file.stage === '读取中' || file.stage === '识别中'" :size="12" class="animate-spin" />
            <CheckCircle2 v-else-if="file.stage === '已完成'" :size="12" class="text-[#0f766e]" />
            <span>{{ sizeText(file.size) }} · {{ file.message }}</span>
          </p>
        </div>
        <button
          type="button"
          class="flex h-8 w-8 items-center justify-center rounded-lg text-[#9aa2b4] transition-colors hover:bg-red-50 hover:text-[#b42318]"
          aria-label="移除文件"
          @click="workspace.removeFile(file.uid)"
        >
          <Trash2 :size="15" />
        </button>
      </div>
    </div>
  </div>
</template>
