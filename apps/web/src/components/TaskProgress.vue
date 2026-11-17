<script setup lang="ts">
import { Check, LoaderCircle, MessageCircleQuestion } from 'lucide-vue-next'
import { workspace } from '../stores/workspace'

const emoji: Record<string, string> = {
  整理师: '🧺',
  复盘师: '📝',
  画像师: '🧭',
  问答教练: '💬',
  审核员: '🔎',
}
</script>

<template>
  <div v-if="workspace.state.bubbles.length" class="space-y-2.5">
    <TransitionGroup
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="opacity-0 translate-y-2"
      move-class="transition duration-300"
    >
      <div
        v-for="bubble in workspace.state.bubbles"
        :key="bubble.id"
        class="flex items-center gap-3 rounded-[16px] border border-white/80 bg-white/75 px-4 py-3 backdrop-blur-sm"
      >
        <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand/10 to-brand-teal/15 text-[18px]">
          {{ emoji[bubble.role] || '✨' }}
        </div>
        <div class="min-w-0 flex-1">
          <p class="text-[12px] font-semibold text-brand">{{ bubble.role }}</p>
          <p class="mt-0.5 text-[13px] text-[#5b6478]">{{ bubble.message }}</p>
        </div>
        <LoaderCircle v-if="bubble.state === '进行中'" :size="16" class="shrink-0 animate-spin text-brand/60" />
        <Check v-else-if="bubble.state === '完成'" :size="16" class="shrink-0 text-[#0f766e]" />
        <MessageCircleQuestion v-else :size="16" class="shrink-0 text-[#b45309]" />
      </div>
    </TransitionGroup>
  </div>
</template>
