<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { AlertCircle, CheckCircle2, Clock3, FileText, Info, LoaderCircle, MessagesSquare, Paperclip, Trash2, X } from 'lucide-vue-next'
import ChatComposer from '../components/ChatComposer.vue'
import ResultCard from '../components/ResultCard.vue'
import { workspace } from '../stores/workspace'
import { fileSizeText, friendlyStageMessage } from '../utils/friendly'
import type { AgentRoleLabel, UploadFileState } from '../types'

onMounted(() => {
  workspace.loadQuickModels()
  workspace.loadHistory()
})

const historyOpen = ref(false)

function titleOf(task: { user_message?: string | null; intent?: string }): string {
  const text = (task.user_message || '').trim()
  if (!text) return '一次对话'
  return text.length > 28 ? `${text.slice(0, 28)}…` : text
}

function timeOf(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  return `${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

async function openHistory(taskId: string): Promise<void> {
  historyOpen.value = false
  await workspace.openTask(taskId)
}

const agentEmoji: Record<AgentRoleLabel, string> = {
  整理师: '🧺',
  复盘师: '📝',
  画像师: '🧭',
  问答教练: '💬',
  审核员: '🔎',
}

const scrollArea = ref<HTMLElement | null>(null)

const noticeIcon = computed(() =>
  workspace.state.noticeKind === 'error' ? AlertCircle : workspace.state.noticeKind === 'success' ? CheckCircle2 : Info,
)

watch(
  () => workspace.state.messages.map((item) => `${item.kind}:${item.text}`).join('\n'),
  async () => {
    await nextTick()
    const element = scrollArea.value
    if (element) element.scrollTo({ top: element.scrollHeight, behavior: 'smooth' })
  },
)

function filesOfMessage(message: { fileUids?: string[] }): UploadFileState[] {
  return (message.fileUids || [])
    .map((uid) => workspace.state.files.find((file) => file.uid === uid))
    .filter((file): file is UploadFileState => Boolean(file))
}
</script>

<template>
  <div class="home-view relative h-[calc(100vh_-_68px)] overflow-hidden">
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="absolute -left-24 -top-24 h-80 w-80 rounded-full bg-brand/10 blur-3xl animate-float"></div>
      <div class="absolute -right-16 top-40 h-72 w-72 rounded-full bg-brand-teal/10 blur-3xl animate-float" style="animation-delay: -3s"></div>
    </div>

    <div class="relative mx-auto flex h-full w-full max-w-[820px] flex-col px-5">
      <div
        class="relative z-40 shrink-0 text-center animate-fade-up"
        :class="workspace.hasStarted ? 'pb-2 pt-4' : 'pb-4 pt-8 sm:pt-10'"
      >
        <button
          type="button"
          class="absolute right-0 top-3 flex items-center gap-1.5 rounded-full border border-[#e4e8f0] bg-white px-3.5 py-1.5 text-[12px] font-medium text-[#5b6478] shadow-sm transition hover:border-brand/30 hover:text-brand"
          @click="historyOpen = !historyOpen; workspace.loadHistory()"
        >
          <Clock3 :size="14" /> 历史对话
        </button>

        <div
          v-if="historyOpen"
          class="absolute right-0 top-12 z-30 w-[320px] max-w-[88vw] rounded-[16px] border border-[#e4e8f0] bg-white p-2 text-left shadow-xl animate-fade-up"
        >
          <div class="flex items-center justify-between px-2 py-1.5">
            <span class="text-[13px] font-semibold text-ink">过往对话</span>
            <button type="button" class="rounded-full p-1 text-muted hover:bg-[#f4f6fa] hover:text-ink" @click="historyOpen = false">
              <X :size="14" />
            </button>
          </div>
          <div v-if="workspace.state.historyLoading" class="flex items-center gap-2 px-2 py-6 text-[12px] text-muted">
            <LoaderCircle :size="14" class="animate-spin text-brand" /> 正在找过往对话…
          </div>
          <div v-else-if="!workspace.state.history.length" class="px-2 py-6 text-center text-[12px] text-muted">
            还没有历史对话，聊过几次后就会出现在这里。
          </div>
          <button
            v-else
            v-for="task in workspace.state.history"
            :key="task.task_id"
            type="button"
            class="flex w-full flex-col gap-1 rounded-[12px] px-3 py-2.5 text-left transition hover:bg-[#f7f8fc]"
            @click="openHistory(task.task_id)"
          >
            <span class="line-clamp-2 text-[12px] font-medium leading-snug text-ink">{{ titleOf(task) }}</span>
            <span class="flex items-center gap-2 text-[11px] text-muted">
              <span>{{ timeOf(task.created_at) }}</span>
              <span class="rounded-full bg-[#eef0ff] px-1.5 py-0.5 text-brand">
                {{ task.intent === 'free' ? '聊天' : task.intent === 'growth' ? '画像' : '复盘' }}
              </span>
              <span v-if="task.stage === 'DONE'" class="text-[#0f766e]">已完成</span>
              <span v-else-if="task.stage === 'FAILED'" class="text-[#b42318]">未完成</span>
            </span>
          </button>
        </div>

        <div
          v-if="!workspace.hasStarted"
          class="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-[16px] bg-gradient-to-br from-brand to-brand-teal text-white shadow-glow"
        >
          <MessagesSquare :size="21" />
        </div>
        <h1
          class="font-semibold leading-tight tracking-tight text-ink"
          :class="workspace.hasStarted ? 'text-[19px]' : 'text-[28px]'"
        >
          把对话交给我
        </h1>
        <p v-if="!workspace.hasStarted" class="mt-1.5 text-[13px] text-[#7a839a]">帮你整理成看得见的成长记录</p>
      </div>

      <div ref="scrollArea" class="min-h-0 w-full flex-1 space-y-3 overflow-y-auto overscroll-contain py-3 pr-1">
        <template v-if="workspace.state.messages.length">
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
            v-else-if="message.kind === 'working'"
            class="flex items-center gap-2 rounded-[14px] border border-brand/10 bg-white/80 px-4 py-3 text-[13px] text-[#5b6478] shadow-sm animate-fade-up"
          >
            <LoaderCircle :size="14" class="shrink-0 animate-spin text-brand" />
            {{ message.text }}
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
        </template>
        <p v-else class="pt-10 text-center text-[13px] text-[#a3abbb]">
          在上面选个方向，或者直接说说想整理什么
        </p>
      </div>

      <div class="shrink-0 space-y-3 pb-4 pt-2">
        <div class="w-full animate-fade-up" style="animation-delay: .06s">
          <ChatComposer />
        </div>

        <div v-if="workspace.state.bubbles.length" class="flex items-center gap-2 pl-1 text-[12px] text-[#9aa2b4] animate-fade-up">
        <span class="inline-block h-1.5 w-1.5 rounded-full bg-gradient-to-r from-brand to-brand-teal"></span>
        {{ friendlyStageMessage(workspace.state.stage) }}
      </div>

        <div v-if="workspace.state.confirmPrompt" class="w-full animate-fade-up rounded-[16px] border border-[#b45309]/20 bg-[#fff9ee] p-4">
        <p class="text-[14px] leading-relaxed text-[#7a4a12]">{{ workspace.state.confirmPrompt }}</p>
        <div class="mt-4 flex gap-2.5">
          <button type="button" class="btn small" @click="workspace.confirm(true)">好，按这个来</button>
          <button type="button" class="btn ghost small" @click="workspace.confirm(false)">再想想</button>
        </div>
      </div>

        <div
          v-if="workspace.state.notice"
          class="flex w-full items-center gap-2.5 rounded-[14px] border px-4 py-3 text-[13px] animate-fade-up"
        :class="workspace.state.noticeKind === 'error'
          ? 'border-red-100 bg-red-50 text-[#b42318]'
          : workspace.state.noticeKind === 'success'
            ? 'border-teal-100 bg-teal-50 text-[#0f766e]'
            : 'border-brand/10 bg-brand/5 text-brand'"
      >
        <component :is="noticeIcon" :size="16" class="shrink-0" />
        <span>{{ workspace.state.notice }}</span>
      </div>

        <p class="pt-1 text-center text-[10px] text-[#b0b6c4]">
          整理 · 复盘 · 画像 · 问答，由几位小伙伴一起完成
        </p>
      </div>
    </div>
  </div>
</template>
