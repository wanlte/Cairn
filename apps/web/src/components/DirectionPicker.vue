<script setup lang="ts">
import { Check, Pencil } from 'lucide-vue-next'
import { workspace } from '../stores/workspace'
import { DIRECTION_OPTIONS } from '../utils/direction'
import type { DirectionKey } from '../types'

function choose(key: DirectionKey): void {
  workspace.setDirection(key)
}
</script>

<template>
  <div>
    <div class="mb-2.5 flex items-center gap-2">
      <span class="text-[13px] font-semibold text-ink">想从哪个方向开始？</span>
      <span v-if="workspace.state.recommendReason" class="flex items-center gap-1 rounded-full bg-brand-teal/10 px-2.5 py-0.5 text-[11px] font-medium text-[#0f766e]">
        <Check :size="12" /> 为你推荐，可以改
      </span>
    </div>

    <div class="flex flex-wrap gap-2">
      <button
        v-for="option in DIRECTION_OPTIONS"
        :key="option.key"
        type="button"
        class="group relative rounded-full border px-4 py-2 text-[13px] font-medium transition-all duration-200"
        :class="workspace.state.direction === option.key
          ? 'border-transparent bg-gradient-to-r from-brand to-brand-light text-white shadow-glow'
          : 'border-[#e4e8f0] bg-white/80 text-[#5b6478] hover:border-brand/40 hover:text-brand'"
        :title="option.description"
        @click="choose(option.key)"
      >
        <Check v-if="workspace.state.direction === option.key" :size="13" class="mr-1 inline" />
        {{ option.label }}
      </button>
    </div>

    <p v-if="workspace.state.recommendReason" class="mt-2.5 text-[12px] leading-relaxed text-[#7a839a]">
      {{ workspace.state.recommendReason }}
    </p>

    <div class="mt-3 flex items-center gap-2">
      <Pencil :size="14" class="shrink-0 text-[#9aa2b4]" />
      <input
        :value="workspace.state.customDirection"
        class="border-0 border-b border-[#e4e8f0] bg-transparent px-1 py-1.5 text-[13px] text-ink outline-none placeholder:text-[#aab1c2] focus:border-brand"
        placeholder="或者用自己的话说想看什么"
        @input="workspace.setCustomDirection(($event.target as HTMLInputElement).value)"
      />
    </div>
  </div>
</template>
