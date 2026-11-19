<script setup lang="ts">
import { computed } from 'vue'
import { Check, Pencil } from 'lucide-vue-next'
import { workspace } from '../stores/workspace'
import { DIRECTION_LABELS, DIRECTION_OPTIONS, directionPrompt } from '../utils/direction'
import type { DirectionKey } from '../types'

const currentLabel = computed(() => DIRECTION_LABELS[workspace.state.direction])
const currentPrompt = computed(() =>
  workspace.state.customDirection || directionPrompt(workspace.state.direction),
)
const hasSelection = computed(
  () => workspace.state.direction !== 'free' || Boolean(workspace.state.customDirection),
)

function choose(key: DirectionKey): void {
  workspace.chooseDirection(key)
}
</script>

<template>
  <div>
    <div class="mb-2 flex flex-wrap items-center gap-2">
      <span class="text-[12px] font-semibold text-ink">想从哪个方向开始？</span>
      <span
        v-if="workspace.state.recommendReason"
        class="flex items-center gap-1 rounded-full bg-brand-teal/10 px-2 py-0.5 text-[10px] font-medium text-[#0f766e]"
      >
        <Check :size="11" /> 为你推荐，可以改
      </span>
    </div>

    <div class="flex flex-wrap gap-1.5">
      <button
        v-for="option in DIRECTION_OPTIONS"
        :key="option.key"
        type="button"
        class="rounded-full border px-3 py-1.5 text-[12px] font-medium transition-all duration-200"
        :class="workspace.state.direction === option.key && !workspace.state.customDirection
          ? 'border-transparent bg-gradient-to-r from-brand to-brand-light text-white shadow-glow'
          : 'border-[#e4e8f0] bg-white/80 text-[#5b6478] hover:border-brand/40 hover:text-brand'"
        :title="option.description"
        @click="choose(option.key)"
      >
        <Check
          v-if="workspace.state.direction === option.key && !workspace.state.customDirection"
          :size="12"
          class="mr-1 inline"
        />
        {{ option.label }}
      </button>
    </div>

    <div
      v-if="hasSelection"
      class="mt-2.5 flex items-start gap-2 rounded-[12px] bg-brand/5 px-3 py-2 animate-fade-up"
    >
      <span class="shrink-0 rounded-full bg-white px-2 py-0.5 text-[10px] font-bold text-brand shadow-sm">
        方向 · {{ currentLabel }}
      </span>
      <p class="min-w-0 text-[11px] leading-relaxed text-[#5b6478]">{{ currentPrompt }}</p>
    </div>

    <div class="mt-2.5 flex items-center gap-2">
      <Pencil :size="13" class="shrink-0 text-[#9aa2b4]" />
      <input
        :value="workspace.state.customDirection"
        class="min-w-0 flex-1 border-0 border-b border-[#e4e8f0] bg-transparent px-1 py-1 text-[12px] text-ink outline-none placeholder:text-[#aab1c2] focus:border-brand"
        placeholder="或者用自己的话说想看什么"
        @input="workspace.setCustomDirection(($event.target as HTMLInputElement).value)"
      />
    </div>

    <p v-if="workspace.state.recommendReason" class="mt-2 text-[11px] leading-relaxed text-[#9aa2b4]">
      {{ workspace.state.recommendReason }}
    </p>
  </div>
</template>
