<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { auth } from '../stores/auth'
import { ApiError } from '../api/client'

const router = useRouter()
const email = ref('local@cairn.dev')
const password = ref('password123')
const error = ref('')
const busy = ref(false)

async function submit(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    await auth.login(email.value, password.value)
    router.push('/import')
  } catch (err) {
    error.value = err instanceof ApiError ? err.body?.message || err.message : '登录失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-card">
    <p class="eyebrow">CAIRN · LOCAL WORKSPACE</p>
    <h1>欢迎回来</h1>
    <p>把散落在各平台的 AI 对话，变成可追溯的成长档案。</p>

    <form @submit.prevent="submit" style="margin-top: 26px">
      <div class="field">
        <label>邮箱</label>
        <input v-model="email" type="email" required autocomplete="username" />
      </div>
      <div class="field">
        <label>密码</label>
        <input v-model="password" type="password" required autocomplete="current-password" />
      </div>
      <button class="btn" type="submit" :disabled="busy" style="width: 100%; margin-top: 8px">
        {{ busy ? '进入中…' : '进入工作区' }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
    </form>

    <div class="tip" style="margin-top: 20px">
      首次输入任意邮箱和密码即可注册；数据保存在本机 PostgreSQL。
    </div>
  </div>
</template>
