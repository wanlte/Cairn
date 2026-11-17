<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth } from './stores/auth'

const route = useRoute()
const router = useRouter()

const nav = [
  { path: '/import', label: '导入台', icon: '↥', hint: '采集与抽取' },
  { path: '/review', label: '复盘', icon: '◇', hint: '每周判断' },
  { path: '/profile', label: '画像', icon: '◎', hint: '成长轨迹' },
  { path: '/chat', label: '问答', icon: '⌁', hint: '检索记忆' },
  { path: '/settings', label: '设置', icon: '⚙', hint: '凭证与用量' },
]

const currentLabel = computed(
  () => nav.find((item) => item.path === route.path)?.label || 'Cairn',
)

function logout(): void {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div v-if="route.name === 'login'" class="login-shell">
    <router-view />
  </div>
  <div v-else class="app-shell">
    <aside class="sidebar">
      <div class="brand" @click="router.push('/import')">
        <div class="brand-mark">C</div>
        <div>
          <strong>Cairn</strong>
          <span>成长档案</span>
        </div>
      </div>

      <nav class="nav">
        <button
          v-for="item in nav"
          :key="item.path"
          class="nav-item"
          :class="{ active: route.path === item.path }"
          @click="router.push(item.path)"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-copy">
            <strong>{{ item.label }}</strong>
            <small>{{ item.hint }}</small>
          </span>
        </button>
      </nav>

      <div class="sidebar-foot">
        <div class="status-dot"></div>
        <span>本地工作区已连接</span>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div>
          <p class="eyebrow">CAIRN / {{ currentLabel }}</p>
          <h1>{{ currentLabel }}</h1>
        </div>
        <div class="topbar-right">
          <span class="user-pill">{{ auth.state.email || '本地用户' }}</span>
          <button class="btn ghost" @click="logout">退出</button>
        </div>
      </header>

      <section class="content">
        <router-view />
      </section>
    </main>
  </div>
</template>
