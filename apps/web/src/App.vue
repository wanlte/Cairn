<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronDown, LogOut, SlidersHorizontal, Sparkles } from 'lucide-vue-next'
import { auth } from './stores/auth'
import { workspace } from './stores/workspace'
import ModelQuickPanel from './components/ModelQuickPanel.vue'

const route = useRoute()
const router = useRouter()
const modelOpen = ref(false)

const onHome = computed(() => route.name === 'home')
const onData = computed(() => route.name === 'data')
const onLab = computed(() => route.name === 'lab')
const onMetrics = computed(() => route.name === 'metrics')
const onReports = computed(() => route.name === 'reports' || route.name === 'report-detail')
const modelSummary = computed(() => {
  const model = workspace.state.model
  const mode = model.credentialMode === '临时使用' ? '临时用一次' : model.credentialMode === '已保存凭证' ? '已保存' : '本机配置'
  return `${model.providerLabel} · ${mode}`
})

function go(name: 'home' | 'profile' | 'reports' | 'data' | 'lab' | 'metrics'): void {
  router.push({ name })
}

function logout(): void {
  workspace.reset()
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div v-if="route.name === 'login'" class="login-shell">
    <router-view />
  </div>
  <div v-else class="min-h-screen bg-canvas">
    <header class="fixed inset-x-0 top-0 z-40 h-[68px] border-b border-white/70 bg-white/80 backdrop-blur-xl">
      <div class="mx-auto flex h-full max-w-[1200px] items-center justify-between px-5">
        <button type="button" class="flex items-center gap-2.5" @click="go('home')">
          <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-brand-teal text-white shadow-glow">
            <Sparkles :size="18" />
          </span>
          <span class="text-[17px] font-semibold tracking-tight text-ink">Cairn</span>
        </button>

        <nav class="flex items-center gap-1 rounded-full bg-[#f1f3fa] p-1">
          <button
            type="button"
            class="rounded-full px-5 py-1.5 text-[13px] font-semibold transition-all duration-200"
            :class="onHome ? 'bg-white text-brand shadow-sm' : 'text-[#7a839a] hover:text-ink'"
            @click="go('home')"
          >
            对话
          </button>
          <button
            type="button"
            class="rounded-full px-5 py-1.5 text-[13px] font-semibold transition-all duration-200"
            :class="route.name === 'profile' ? 'bg-white text-brand shadow-sm' : 'text-[#7a839a] hover:text-ink'"
            @click="go('profile')"
          >
            画像
          </button>
          <button
            type="button"
            class="rounded-full px-5 py-1.5 text-[13px] font-semibold transition-all duration-200"
            :class="onData ? 'bg-white text-brand shadow-sm' : 'text-[#7a839a] hover:text-ink'"
            @click="go('data')"
          >
            数据
          </button>
          <button
            type="button"
            class="rounded-full px-5 py-1.5 text-[13px] font-semibold transition-all duration-200"
            :class="onLab ? 'bg-white text-brand shadow-sm' : 'text-[#7a839a] hover:text-ink'"
            @click="go('lab')"
          >
            实验室
          </button>
          <button
            type="button"
            class="rounded-full px-5 py-1.5 text-[13px] font-semibold transition-all duration-200"
            :class="onMetrics ? 'bg-white text-brand shadow-sm' : 'text-[#7a839a] hover:text-ink'"
            @click="go('metrics')"
          >
            评测
          </button>
          <button
            type="button"
            class="rounded-full px-5 py-1.5 text-[13px] font-semibold transition-all duration-200"
            :class="onReports ? 'bg-white text-brand shadow-sm' : 'text-[#7a839a] hover:text-ink'"
            @click="go('reports')"
          >
            报告
          </button>
        </nav>

        <div class="flex items-center gap-2">
          <div class="relative">
            <button
              type="button"
              class="hidden items-center gap-1.5 rounded-full border border-[#e4e8f0] bg-white/80 px-3 py-2 text-[12px] font-medium text-[#5b6478] transition-colors hover:border-brand/40 hover:text-brand sm:flex"
              @click="modelOpen = !modelOpen"
            >
              <SlidersHorizontal :size="14" />
              {{ modelSummary }}
              <ChevronDown :size="13" :class="modelOpen ? 'rotate-180 transition-transform' : 'transition-transform'" />
            </button>
            <button
              type="button"
              class="flex h-9 w-9 items-center justify-center rounded-full border border-[#e4e8f0] bg-white text-[#5b6478] sm:hidden"
              aria-label="模型设置"
              @click="modelOpen = !modelOpen"
            >
              <SlidersHorizontal :size="16" />
            </button>
            <ModelQuickPanel :open="modelOpen" @close="modelOpen = false" />
          </div>
          <button
            type="button"
            class="flex h-9 w-9 items-center justify-center rounded-full text-[#9aa2b4] transition-colors hover:bg-red-50 hover:text-[#b42318]"
            aria-label="退出登录"
            @click="logout"
          >
            <LogOut :size="16" />
          </button>
        </div>
      </div>
    </header>

    <main class="min-h-screen pt-[68px]">
      <router-view />
    </main>
  </div>
</template>
