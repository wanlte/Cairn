<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AlertTriangle,
  Check,
  GitBranch,
  LoaderCircle,
  ShieldAlert,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-vue-next'
import { analysisApi } from '../api/client'
import type { EvidenceChain, ReviewItem } from '../types'
import {
  friendlyAttribution,
  friendlyError,
  friendlyVerdict,
  verdictTone,
} from '../utils/friendly'
import { text } from '../utils/review'

const props = defineProps<{ item: ReviewItem; busy: boolean }>()
const emit = defineEmits<{ (event: 'feedback', decision: 'AGREE' | 'DISAGREE'): void }>()

const chain = ref<EvidenceChain | null>(null)
const loadingChain = ref(false)
const appealOpen = ref(false)
const appealReason = ref('')
const appealBusy = ref(false)
const appealStatus = ref(props.item.appeal_status || 'NONE')
const localError = ref('')

const confidenceText = computed(() => {
  const low = props.item.confidence_low
  const high = props.item.confidence_high
  if (low == null || high == null) return ''
  return `把握 ${Math.round(low * 100)}%–${Math.round(high * 100)}%`
})

async function toggleChain(): Promise<void> {
  if (chain.value) {
    chain.value = null
    return
  }
  loadingChain.value = true
  localError.value = ''
  try {
    chain.value = await analysisApi.evidenceChain(props.item.id)
  } catch (err) {
    localError.value = friendlyError(err)
  } finally {
    loadingChain.value = false
  }
}

async function submitAppeal(): Promise<void> {
  if (!appealReason.value.trim()) return
  appealBusy.value = true
  localError.value = ''
  try {
    await analysisApi.submitAppeal(props.item.id, appealReason.value.trim())
    appealStatus.value = 'PENDING'
    appealOpen.value = false
    appealReason.value = ''
  } catch (err) {
    localError.value = friendlyError(err)
  } finally {
    appealBusy.value = false
  }
}
</script>

<template>
  <article class="rounded-[14px] bg-[#f8fafc] px-4 py-3.5">
    <div class="mb-2 flex flex-wrap items-center gap-2">
      <span class="rounded-full px-2.5 py-1 text-[11px] font-semibold" :class="verdictTone(item.verdict)">
        {{ friendlyVerdict(item.verdict) }}
      </span>
      <span v-if="confidenceText" class="badge gray">{{ confidenceText }}</span>
      <span v-if="friendlyAttribution(item.attribution)" class="text-[11px] text-[#8b93a7]">
        {{ friendlyAttribution(item.attribution) }}
      </span>
      <span v-if="item.conflicts_with?.length" class="badge amber">
        与另外 {{ item.conflicts_with.length }} 条结论冲突
      </span>
      <span v-if="appealStatus === 'PENDING'" class="badge blue">复核中</span>
      <span v-else-if="appealStatus === 'ACCEPTED'" class="badge green">已按你说的修订</span>
    </div>

    <p class="text-[13px] leading-relaxed text-[#434c60]">{{ text(item.payload, 'reason') }}</p>

    <button
      type="button"
      class="mt-3 flex items-center gap-1.5 text-[12px] font-medium text-brand hover:underline"
      :disabled="loadingChain"
      @click="toggleChain"
    >
      <LoaderCircle v-if="loadingChain" :size="13" class="animate-spin" />
      <GitBranch v-else :size="13" />
      {{ chain ? '收起推理过程' : '看看这条怎么来的' }}
    </button>

    <div v-if="chain" class="mt-3 rounded-[12px] border border-brand/15 bg-white px-3.5 py-3">
      <p class="text-[11px] font-semibold text-[#8b93a7]">从证据到结论</p>
      <ol class="mt-2 space-y-1.5">
        <li v-for="(step, index) in chain.reasoning_chain" :key="index" class="flex gap-2 text-[12px] leading-relaxed text-[#5b6478]">
          <span class="text-brand">{{ index + 1 }}.</span> {{ step }}
        </li>
      </ol>
      <p v-if="!chain.reasoning_chain.length" class="mt-2 text-[12px] text-[#9aa2b4]">这条结论没有留下推理步骤。</p>
      <p class="mt-2 text-[11px] text-[#9aa2b4]">引用了 {{ chain.evidence.length }} 条原始记录</p>
    </div>

    <div v-if="localError" class="mt-2 text-[12px] text-[#b42318]">{{ localError }}</div>

    <div class="mt-3 flex flex-wrap items-center gap-2">
      <template v-if="!item.feedback?.decision">
        <button type="button" class="btn ghost small" :disabled="busy" @click="emit('feedback', 'AGREE')">
          <ThumbsUp :size="13" class="mr-1 inline" /> 认同
        </button>
        <button type="button" class="btn ghost small" :disabled="busy" @click="emit('feedback', 'DISAGREE')">
          <ThumbsDown :size="13" class="mr-1 inline" /> 不太对
        </button>
      </template>
      <span v-else class="inline-flex items-center gap-1 text-[11px] font-medium text-[#0f766e]">
        <Check :size="12" /> 你标记了「{{ item.feedback.decision === 'AGREE' ? '认同' : '不太对' }}」
      </span>
      <button
        v-if="appealStatus === 'NONE'"
        type="button"
        class="btn ghost small"
        @click="appealOpen = !appealOpen"
      >
        <ShieldAlert :size="13" class="mr-1 inline" /> 这条不准，申诉
      </button>
    </div>

    <div v-if="appealOpen" class="mt-3 rounded-[12px] border border-[#e4e8f0] bg-white p-3">
      <textarea
        v-model="appealReason"
        rows="2"
        class="w-full resize-none text-[12px]"
        placeholder="说说当时真实的情况，系统会重新看这条结论"
      />
      <div class="mt-2 flex items-center gap-2">
        <button type="button" class="btn small" :disabled="appealBusy || !appealReason.trim()" @click="submitAppeal">
          <LoaderCircle v-if="appealBusy" :size="13" class="animate-spin" />
          <AlertTriangle v-else :size="13" />
          提交申诉
        </button>
        <button type="button" class="btn ghost small" @click="appealOpen = false">算了</button>
      </div>
    </div>
  </article>
</template>
