<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { AlertCircle, CheckCircle2, Info, MessagesSquare } from 'lucide-vue-next'
import ChatComposer from '../components/ChatComposer.vue'
import FileDropzone from '../components/FileDropzone.vue'
import DirectionPicker from '../components/DirectionPicker.vue'
import TaskProgress from '../components/TaskProgress.vue'
import ResultCard from '../components/ResultCard.vue'
import { workspace } from '../stores/workspace'
import { friendlyStageMessage } from '../utils/friendly'

onMounted(() => {
  workspace.loadQuickModels()
})

const noticeIcon = computed(() =>
  workspace.state.noticeKind === 'error' ? AlertCircle : workspace.state.noticeKind === 'success' ? CheckCircle2 : Info,
)
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
          v-for="message in workspace.state.messages.filter((item) => item.kind !== 'result')"
          :key="message.id"
          class="flex animate-fade-up"
          :class="message.role === '用户' ? 'justify-end' : 'justify-start'"
        >
          <div
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

      <div class="mt-5 grid w-full gap-4 animate-fade-up sm:grid-cols-2" style="animation-delay: .12s">
        <div class="rounded-[20px] border border-white/80 bg-white/70 p-5 shadow-soft backdrop-blur-sm">
          <FileDropzone />
        </div>
        <div class="rounded-[20px] border border-white/80 bg-white/70 p-5 shadow-soft backdrop-blur-sm">
          <DirectionPicker />
        </div>
      </div>

      <div class="mt-5 w-full animate-fade-up" style="animation-delay: .18s">
        <div class="mb-2.5 flex items-center gap-2 pl-1">
          <span class="inline-block h-1.5 w-1.5 rounded-full bg-gradient-to-r from-brand to-brand-teal"></span>
          <span class="text-[12px] font-semibold text-[#7a839a]">
            协作进度 · {{ friendlyStageMessage(workspace.state.stage) }}
          </span>
        </div>
        <TaskProgress />
      </div>

      <div v-if="workspace.state.confirmPrompt" class="mt-5 w-full animate-fade-up rounded-[20px] border border-[#b45309]/20 bg-[#fff9ee] p-5">
        <p class="text-[14px] leading-relaxed text-[#7a4a12]">{{ workspace.state.confirmPrompt }}</p>
        <div class="mt-4 flex gap-2.5">
          <button type="button" class="btn small" @click="workspace.confirm(true)">好，按这个来</button>
          <button type="button" class="btn ghost small" @click="workspace.confirm(false)">再想想</button>
        </div>
      </div>

      <div v-if="workspace.state.result" class="mt-5 w-full">
        <ResultCard :result="workspace.state.result" @next="workspace.setDirection('free')" />
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
