<script setup lang="ts">
import { ArrowRight, Check } from 'lucide-vue-next'
import type { AgentResult } from '../types'

defineProps<{ result: AgentResult }>()
const emit = defineEmits<{ (event: 'next'): void }>()
</script>

<template>
  <div class="animate-fade-up overflow-hidden rounded-[20px] border border-white/80 bg-white/90 shadow-soft">
    <div class="h-1 bg-gradient-to-r from-brand via-brand-light to-brand-teal"></div>
    <div class="p-6">
      <div class="mb-3 flex items-center gap-2">
        <span class="rounded-full bg-brand/10 px-3 py-1 text-[11px] font-semibold text-brand">{{ result.kind }}</span>
        <h3 class="text-[18px] font-semibold text-ink">{{ result.title }}</h3>
      </div>
      <p class="whitespace-pre-wrap text-[14px] leading-[1.9] text-[#434c60]">{{ result.summary }}</p>

      <div v-if="result.suggestions.length" class="mt-5">
        <p class="mb-2.5 flex items-center gap-1.5 text-[12px] font-semibold text-[#5b6478]">
          <Check :size="14" class="text-[#0f766e]" /> 接下来可以试试
        </p>
        <ul class="space-y-2">
          <li
            v-for="(item, index) in result.suggestions"
            :key="index"
            class="flex items-start gap-2.5 rounded-[12px] bg-[#f8fafc] px-3.5 py-2.5 text-[13px] leading-relaxed text-[#5b6478]"
          >
            <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gradient-to-br from-brand to-brand-teal"></span>
            <span>{{ item }}</span>
          </li>
        </ul>
      </div>

      <button
        v-if="result.nextLabel"
        type="button"
        class="mt-5 inline-flex items-center gap-1.5 rounded-full bg-brand/5 px-4 py-2 text-[13px] font-semibold text-brand transition-colors hover:bg-brand/10"
        @click="emit('next')"
      >
        {{ result.nextLabel }} <ArrowRight :size="14" />
      </button>
    </div>
  </div>
</template>
