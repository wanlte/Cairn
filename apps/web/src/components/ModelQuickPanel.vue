<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, ChevronDown, KeyRound, Laptop, LockKeyhole, Server, X } from 'lucide-vue-next'
import { workspace } from '../stores/workspace'
import type { CredentialMode, ProviderLabel } from '../types'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (event: 'close'): void }>()

const tempKey = ref('')
const tempBaseUrl = ref('')
const tempModel = ref('')
const expanded = ref<ProviderLabel | null>(null)

const labels: ProviderLabel[] = ['深度求索', '火山引擎', '腾讯混元', '兼容接口']
const providerMap: Record<ProviderLabel, string> = {
  深度求索: 'deepseek',
  火山引擎: 'volcengine',
  腾讯混元: 'hunyuan',
  兼容接口: 'openai_compat',
}

const selectedProvider = computed(() => workspace.state.model.providerLabel)

function selectProvider(label: ProviderLabel): void {
  expanded.value = expanded.value === label ? null : label
  const provider = providerMap[label]
  const option = workspace.state.quickModels.find((item) => item.provider === provider)
  workspace.setModel({
    providerLabel: label,
    provider,
    model: option?.model || workspace.state.model.model,
  })
}

function chooseMode(mode: CredentialMode, credentialId: number | null = null): void {
  workspace.setModel({ credentialMode: mode, credentialId, temporaryKey: null })
}

function chooseSaved(provider: string, credentialId: number, model: string | null): void {
  workspace.setModel({
    provider,
    credentialId,
    model,
    credentialMode: '已保存凭证',
    temporaryKey: null,
  })
}

function savedFor(label: ProviderLabel) {
  return workspace.state.quickModels.filter((item) => item.label === label && item.saved.length > 0)
}

function applyTemp(): void {
  if (!tempKey.value.trim()) return
  workspace.setModel({
    credentialMode: '临时使用',
    credentialId: null,
    temporaryKey: tempKey.value.trim(),
  })
  tempKey.value = ''
  tempBaseUrl.value = ''
  tempModel.value = ''
  emit('close')
}

function close(): void {
  tempKey.value = ''
  emit('close')
}
</script>

<template>
  <Transition
    enter-active-class="transition duration-200 ease-out"
    enter-from-class="opacity-0 -translate-y-2"
    leave-active-class="transition duration-150 ease-in"
    leave-to-class="opacity-0 -translate-y-2"
  >
    <div v-if="props.open" class="absolute right-0 top-[calc(100%+12px)] z-50 w-[360px] max-w-[calc(100vw-32px)]">
      <div class="overflow-hidden rounded-[20px] border border-white/80 bg-white/95 shadow-soft backdrop-blur-xl">
        <div class="flex items-center justify-between border-b border-[#eef0f6] px-5 py-4">
          <div>
            <p class="text-[15px] font-semibold text-ink">选个模型帮忙</p>
            <p class="mt-0.5 text-[11px] text-[#8b93a7]">随时可改，临时密钥不会被保存</p>
          </div>
          <button type="button" class="flex h-8 w-8 items-center justify-center rounded-lg text-[#9aa2b4] hover:bg-[#f1f4f9]" aria-label="关闭" @click="close">
            <X :size="16" />
          </button>
        </div>

        <div class="max-h-[60vh] overflow-y-auto px-5 py-4">
          <p class="mb-2 text-[12px] font-semibold text-[#5b6478]">服务商</p>
          <div class="space-y-1.5">
            <div v-for="label in labels" :key="label">
              <button
                type="button"
                class="flex w-full items-center justify-between rounded-xl border px-3.5 py-2.5 text-[13px] transition-colors"
                :class="selectedProvider === label ? 'border-brand/40 bg-brand/5 text-brand' : 'border-[#eef0f6] text-[#5b6478] hover:bg-[#f8fafc]'"
                @click="selectProvider(label)"
              >
                <span class="flex items-center gap-2">
                  <Check v-if="selectedProvider === label" :size="14" />
                  {{ label }}
                </span>
                <ChevronDown :size="14" :class="expanded === label ? 'rotate-180 transition-transform' : 'transition-transform'" />
              </button>

              <div v-if="expanded === label" class="mt-2 space-y-2 rounded-xl bg-[#f8fafc] p-3 animate-fade-up">
                <button
                  type="button"
                  class="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[12px] transition-colors hover:bg-white"
                  :class="workspace.state.model.credentialMode === '本机配置' && workspace.state.model.provider === providerMap[label] ? 'text-brand' : 'text-[#5b6478]'"
                  @click="chooseMode('本机配置'); expanded = null"
                >
                  <Laptop :size="15" /> 用这台电脑上的配置
                </button>

                <template v-for="option in savedFor(label)" :key="option.provider">
                  <button
                    v-for="credential in option.saved"
                    :key="credential.id"
                    type="button"
                    class="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[12px] text-[#5b6478] transition-colors hover:bg-white"
                    @click="chooseSaved(option.provider, credential.id, credential.model); expanded = null"
                  >
                    <Server :size="15" /> 用之前保存的「{{ credential.name }}」
                  </button>
                </template>

                <div class="rounded-lg border border-[#eef0f6] bg-white p-2.5">
                  <p class="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-[#5b6478]">
                    <KeyRound :size="13" /> 临时用一次
                  </p>
                  <input
                    v-model="tempKey"
                    type="password"
                    autocomplete="off"
                    class="mb-2 text-[12px]"
                    placeholder="填入临时密钥"
                  />
                  <input v-if="label === '兼容接口'" v-model="tempBaseUrl" class="mb-2 text-[12px]" placeholder="接口地址（可选）" />
                  <input v-model="tempModel" class="mb-2 text-[12px]" placeholder="模型名称（可选）" />
                  <button
                    type="button"
                    class="flex w-full items-center justify-center gap-1.5 rounded-lg bg-brand px-3 py-2 text-[12px] font-semibold text-white transition-opacity disabled:opacity-40"
                    :disabled="!tempKey.trim()"
                    @click="applyTemp"
                  >
                    <LockKeyhole :size="13" /> 就这样用一次
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>
