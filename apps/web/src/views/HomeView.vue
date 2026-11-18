<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { AlertCircle, CheckCircle2, FileText, Info, LoaderCircle, MessagesSquare, Paperclip, Trash2 } from 'lucide-vue-next'
import ChatComposer from '../components/ChatComposer.vue'
import DirectionPicker from '../components/DirectionPicker.vue'
import ResultCard from '../components/ResultCard.vue'
import { workspace } from '../stores/workspace'
import { fileSizeText, friendlyStageMessage } from '../utils/friendly'
import type { AgentRoleLabel, UploadFileState } from '../types'

onMounted(() => {
  workspace.loadQuickModels()
})

const agentEmoji: Record<AgentRoleLabel, string> = {
  整理师: '🧺',
  复盘师: '📝',
  画像师: '🧭',
  问答教练: '💬',
  审核员: '🔎',
}

const noticeIcon = computed(() =>
  workspace.state.noticeKind === 'error' ? AlertCircle : workspace.state.noticeKind === 'success' ? CheckCircle2 : Info,
)

function filesOfMessage(message: { fileUids?: string[] }): UploadFileState[] {
  return (message.fileUids || [])
    .map((uid) => workspace.state.files.find((file) => file.uid === uid))
    .filter((file): file is UploadFileState => Boolean(file))
}
</script>

<template>
  <div class="home-view relative min-h-full">
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="absolute -left-24 -top-24 h-80 w-80 rounded-full bg-brand/10 blur-3xl animate-float"></div>
      <div class="absolute -right-16 top-40 h-72 w-72 rounded-full bg-brand-teal/10 blur-3xl animate-float" style="animation-delay: -3s"></div>
    </div>

    <div class="relative mx-auto flex w-full max-w-[820px] flex-col items-center px-5 pb-24 pt-14 sm:pt-20">
      <div class="mb-9 text-center animate-fade-up">
        <div class="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-[18px] bg-gradient-to-br from-brand to-brand-teal text-white shadow-glow">
          <MessagesSquare :size="26" />
        </div>
        <h1 class="text-[30px] font-semibold leading-tight tracking-tight text-ink">把对话交给我</h1>
        <p class="mt-2 text-[15px] text-[#7a839a]">帮你整理成看得见的成长记录</p>
      </div>

      <div v-if="workspace.state.messages.length" class="mb-6 w-full space-y-3">
        <div
          v-for="message in workspace.state.messages"
          :key="message.id"
          class="flex animate-fade-up"
          :class="message.kind === 'result' ? 'w-full' : message.role === '用户' ? 'justify-end' : 'justify-start'"
        >
          <div
            v-if="message.kind === 'file'"
            class="w-full max-w-[92%] rounded-[18px] rounded-br-md border border-white/80 bg-white/90 p-3 shadow-sm sm:max-w-[80%]"
          >
            <p class="mb-2 flex items-center gap-1.5 px-1 text-[12px] font-medium text-[#8b93a7]">
              <Paperclip :size="13" /> 带上了 {{ filesOfMessage(message).length }} 份文件
            </p>
            <div class="space-y-1.5">
              <div
                v-for="file in filesOfMessage(message)"
                :key="file.uid"
                class="flex items-center gap-2.5 rounded-[12px] bg-[#f8fafc] px-3 py-2"
              >
                <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                  :class="file.error ? 'bg-red-50 text-[#b42318]' : 'bg-brand/10 text-brand'">
                  <FileText :size="16" />
                </div>
                <div class="min-w-0 flex-1">
                  <p class="truncate text-[13px] font-medium text-ink">{{ file.name }}</p>
                  <p class="mt-0.5 flex items-center gap-1 text-[11px] text-[#8b93a7]">
                    <LoaderCircle v-if="file.stage === '读取中' || file.stage === '识别中'" :size="11" class="animate-spin" />
                    <CheckCircle2 v-else-if="file.stage === '已完成'" :size="11" class="text-[#0f766e]" />
                    {{ fileSizeText(file.size) }} · {{ file.message }}
                  </p>
                </div>
                <button
                  type="button"
                  class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[#9aa2b4] transition-colors hover:bg-red-50 hover:text-[#b42318]"
                  aria-label="移除文件"
                  @click="workspace.removeFile(file.uid)"
                >
                  <Trash2 :size="14" />
                </button>
              </div>
            </div>
          </div>
          <div v-else-if="message.kind === 'result' && message.result" class="w-full">
            <ResultCard :result="message.result" @next="workspace.setDirection('free')" />
          </div>
          <div
            v-else-if="message.kind === 'agent'"
            class="flex max-w-[88%] items-start gap-2.5 rounded-[18px] rounded-bl-md border border-white/80 bg-white/90 px-3.5 py-3 shadow-sm sm:max-w-[80%]"
          >
            <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand/10 to-brand-teal/15 text-[16px]">
              {{ agentEmoji[message.role as AgentRoleLabel] || '✨' }}
            </div>
            <div class="min-w-0">
              <p class="text-[12px] font-semibold text-brand">{{ message.role }}</p>
              <p class="mt-0.5 flex items-center gap-1.5 text-[13px] leading-relaxed text-[#5b6478]">
                <LoaderCircle v-if="message.agentState === '进行中'" :size="13" class="shrink-0 animate-spin text-brand/60" />
                <CheckCircle2 v-else-if="message.agentState === '完成'" :size="13" class="shrink-0 text-[#0f766e]" />
                <AlertCircle v-else :size="13" class="shrink-0 text-[#b45309]" />
                {{ message.text }}
              </p>
            </div>
          </div>
          <div
            v-else-if="message.text"
            class="max-w-[85%] rounded-[18px] px-4 py-3 text-[14px] leading-relaxed shadow-sm"
            :class="message.role === '用户'
              ? 'rounded-br-md bg-gradient-to-br from-brand to-brand-light text-white'
              : 'rounded-bl-md border border-white/80 bg-white/90 text-[#434c60]'"
          >
            {{ message.text }}
          </div>
        </div>
      </div>

      <div class="w-full animate-fade-up" style="animation-delay: .06s">
        <ChatComposer />
      </div>

      <div class="mt-5 w-full animate-fade-up" style="animation-delay: .12s">
        <div class="rounded-[20px] border border-white/80 bg-white/70 p-5 shadow-soft backdrop-blur-sm">
          <DirectionPicker />
        </div>
      </div>

      <div v-if="workspace.state.bubbles.length" class="mt-4 flex items-center gap-2 pl-1 text-[12px] text-[#9aa2b4] animate-fade-up">
        <span class="inline-block h-1.5 w-1.5 rounded-full bg-gradient-to-r from-brand to-brand-teal"></span>
        {{ friendlyStageMessage(workspace.state.stage) }}
      </div>

      <div v-if="workspace.state.confirmPrompt" class="mt-5 w-full animate-fade-up rounded-[20px] border border-[#b45309]/20 bg-[#fff9ee] p-5">
        <p class="text-[14px] leading-relaxed text-[#7a4a12]">{{ workspace.state.confirmPrompt }}</p>
        <div class="mt-4 flex gap-2.5">
          <button type="button" class="btn small" @click="workspace.confirm(true)">好，按这个来</button>
          <button type="button" class="btn ghost small" @click="workspace.confirm(false)">再想想</button>
        </div>
      </div>

      <div
        v-if="workspace.state.notice"
        class="mt-5 flex w-full items-center gap-2.5 rounded-[14px] border px-4 py-3 text-[13px] animate-fade-up"
        :class="workspace.state.noticeKind === 'error'
          ? 'border-red-100 bg-red-50 text-[#b42318]'
          : workspace.state.noticeKind === 'success'
            ? 'border-teal-100 bg-teal-50 text-[#0f766e]'
            : 'border-brand/10 bg-brand/5 text-brand'"
      >
        <component :is="noticeIcon" :size="16" class="shrink-0" />
        <span>{{ workspace.state.notice }}</span>
      </div>

      <p class="mt-12 text-center text-[11px] text-[#b0b6c4]">
        整理 · 复盘 · 画像 · 问答，由几位小伙伴一起完成
      </p>
    </div>
  </div>
</template>
