<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { auth } from '../stores/auth'
import { friendlyError } from '../utils/friendly'

const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    await auth.login(email.value, password.value)
    router.push('/')
  } catch {
    error.value = friendlyError(new Error('unauthorized'))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-card">
    <h1>欢迎回来</h1>
    <p>把散落在各平台的对话，变成看得见的成长记录。</p>

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
      第一次输入邮箱和密码就会为你建好账号，直接进来就好。
    </div>
  </div>
</template>
