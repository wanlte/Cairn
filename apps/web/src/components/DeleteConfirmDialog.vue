<script setup lang="ts">
import { ref, watch } from 'vue'
import { AlertTriangle, LoaderCircle, X } from 'lucide-vue-next'

const props = defineProps<{
  open: boolean
  title: string
  description: string
  busy?: boolean
}>()

const emit = defineEmits<{
  close: []
  confirm: [keepProfile: boolean]
}>()

const keepProfile = ref(true)

watch(
  () => props.open,
  (value) => {
    if (value) keepProfile.value = true
  },
)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[100] flex items-center justify-center bg-[#172033]/35 p-4 backdrop-blur-sm" @click.self="emit('close')">
      <div class="w-full max-w-[420px] rounded-[20px] bg-white p-6 shadow-2xl animate-fade-up">
        <div class="flex items-start justify-between gap-3">
          <div class="flex items-center gap-2">
            <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-red-50 text-[#b42318]">
              <AlertTriangle :size="18" />
            </span>
            <h3 class="text-[16px] font-semibold text-ink">{{ title }}</h3>
          </div>
          <button type="button" class="rounded-full p-1 text-[#9aa2b4] hover:bg-[#f4f6fa]" aria-label="取消" @click="emit('close')">
            <X :size="16" />
          </button>
        </div>

        <p class="mt-3 text-[13px] leading-relaxed text-[#5b6478]">{{ description }}</p>

        <div class="mt-4 rounded-[14px] border border-[#e4e8f0] bg-[#fafbff] p-4">
          <p class="text-[12px] font-semibold text-ink">画像里由这条记录得出的结论怎么办？</p>
          <label class="mt-3 flex cursor-pointer items-start gap-2.5">
            <input v-model="keepProfile" type="radio" :value="true" class="mt-0.5 accent-[#4F46E5]" />
            <span>
              <span class="block text-[12px] font-medium text-ink">保留画像</span>
              <span class="mt-0.5 block text-[11px] leading-relaxed text-muted">画像不变，只是删掉这条记录。</span>
            </span>
          </label>
          <label class="mt-2.5 flex cursor-pointer items-start gap-2.5">
            <input v-model="keepProfile" type="radio" :value="false" class="mt-0.5 accent-[#4F46E5]" />
            <span>
              <span class="block text-[12px] font-medium text-ink">不保留，一起清掉</span>
              <span class="mt-0.5 block text-[11px] leading-relaxed text-muted">只靠这条记录得出的画像结论会作废，也不会再生成。</span>
            </span>
          </label>
        </div>

        <div class="mt-5 flex items-center justify-end gap-2">
          <button type="button" class="btn ghost small" :disabled="busy" @click="emit('close')">取消</button>
          <button
            type="button"
            class="flex items-center gap-1.5 rounded-full bg-[#b42318] px-4 py-2 text-[12px] font-semibold text-white transition hover:bg-[#9a1d14] disabled:opacity-50"
            :disabled="busy"
            @click="emit('confirm', keepProfile)"
          >
            <LoaderCircle v-if="busy" :size="14" class="animate-spin" />
            确认删除
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
