<script setup lang="ts">
import { ref } from 'vue'
import { ArrowRight, CheckCircle2, LoaderCircle } from 'lucide-vue-next'
import { ingestionApi, metricsApi } from '../api/client'
import type { IngestionPreview } from '../types'
import { friendlyError } from '../utils/friendly'

const emit = defineEmits<{ (event: 'imported'): void }>()

const SOURCES = [
  { value: 'wechat', label: '微信', hint: '昵称 时间 + 内容' },
  { value: 'feishu', label: '飞书', hint: '[时间] 姓名：内容' },
  { value: 'email', label: '邮件', hint: 'From / Date / Subject' },
  { value: 'voice', label: '语音转写', hint: '[00:12] 说话人：内容' },
  { value: 'diary', label: '日记', hint: '## 日期 + 内容' },
  { value: 'markdown', label: 'Markdown', hint: '### You / Assistant' },
]

const sourceType = ref('wechat')
const text = ref('')
const preview = ref<IngestionPreview | null>(null)
const busy = ref(false)
const error = ref('')
const done = ref('')

async function buildPreview(): Promise<void> {
  if (!text.value.trim()) return
  busy.value = true
  error.value = ''
  done.value = ''
  preview.value = null
  try {
    preview.value = await ingestionApi.preview({
      source_type: sourceType.value,
      text: text.value,
      filename: `import.${sourceType.value}`,
    })
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busy.value = false
  }
}

async function commit(): Promise<void> {
  if (!preview.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await ingestionApi.commit(preview.value.preview_id)
    done.value = result.duplicate
      ? '这份记录已经在库里了，没有重复导入。'
      : `已经收好 ${result.turn_count} 条记录。`
    preview.value = null
    text.value = ''
    void metricsApi.track('import_completed', { source: sourceType.value })
    emit('imported')
  } catch (err) {
    error.value = friendlyError(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="card animate-fade-up">
    <div class="card-head">
      <div>
        <h2 class="text-[16px] font-semibold text-ink">把别处的记录带进来</h2>
        <p class="mt-1 text-[12px] text-muted">粘贴微信、飞书、邮件、语音转写或日记，先预览再决定要不要收下。</p>
      </div>
    </div>

    <div v-if="error" class="mb-4 rounded-[12px] border border-red-100 bg-red-50 px-4 py-2.5 text-[12px] text-[#b42318]">
      {{ error }}
    </div>
    <div v-if="done" class="mb-4 flex items-center gap-2 rounded-[12px] border border-[#c9eee7] bg-[#e7f6f3] px-4 py-2.5 text-[12px] text-[#0f766e]">
      <CheckCircle2 :size="15" /> {{ done }}
    </div>

    <div class="flex flex-wrap gap-2">
      <button
        v-for="item in SOURCES"
        :key="item.value"
        type="button"
        class="rounded-full px-3 py-1.5 text-[12px] font-medium transition-all"
        :class="sourceType === item.value
          ? 'bg-brand text-white shadow-sm'
          : 'bg-[#f1f3fa] text-[#667085] hover:bg-[#e8ebf5]'"
        @click="sourceType = item.value"
      >
        {{ item.label }}
      </button>
    </div>
    <p class="mt-2 text-[12px] text-muted">
      {{ SOURCES.find((item) => item.value === sourceType)?.hint }}
    </p>

    <textarea
      v-model="text"
      rows="7"
      class="mt-4 w-full resize-none"
      placeholder="把导出的聊天记录、邮件正文或日记粘到这里…"
    />

    <div class="mt-3 flex items-center gap-3">
      <button type="button" class="btn soft" :disabled="busy || !text.trim()" @click="buildPreview">
        <LoaderCircle v-if="busy && !preview" :size="15" class="animate-spin" />
        <ArrowRight v-else :size="15" />
        看看能读出什么
      </button>
      <span class="text-[12px] text-muted">读不准的地方，之后还能一条条改。</span>
    </div>

    <div v-if="preview" class="mt-5 rounded-[14px] border border-[#e4e8f0] bg-[#fcfdff] p-4">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[14px] font-semibold text-ink">{{ preview.title }}</span>
        <span class="badge blue">{{ preview.total_turns }} 条</span>
        <span v-if="preview.low_confidence_count" class="badge amber">
          {{ preview.low_confidence_count }} 条需要留意
        </span>
      </div>
      <div class="list mt-3">
        <div v-for="turn in preview.turns.slice(0, 4)" :key="turn.turn_id" class="list-item text-[12px]">
          <p class="text-ink">{{ turn.user_content || '（没有用户发言）' }}</p>
          <p class="mt-1 text-muted">{{ turn.assistant_content || '（单条记录，没有对话）' }}</p>
        </div>
      </div>
      <p v-if="preview.total_turns > 4" class="mt-2 text-[12px] text-muted">
        还有 {{ preview.total_turns - 4 }} 条，收下后可以在记录里查看。
      </p>
      <div v-for="issue in preview.anomalies.slice(0, 2)" :key="issue" class="mt-2 text-[12px] text-[#b45309]">
        · {{ issue }}
      </div>
      <button type="button" class="btn mt-4" :disabled="busy" @click="commit">收下这些记录</button>
    </div>
  </section>
</template>
