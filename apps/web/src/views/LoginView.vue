<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { auth } from '../stores/auth'
import { friendlyAuthError } from '../utils/friendly'

const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

function switchMode(next: 'login' | 'register'): void {
  mode.value = next
  error.value = ''
}

async function submit(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    if (mode.value === 'register') await auth.register(email.value, password.value)
    else await auth.login(email.value, password.value)
    router.push('/')
  } catch (err) {
    error.value = friendlyAuthError(err, mode.value)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-card">
    <h1>{{ mode === 'register' ? '创建你的账号' : '欢迎回来' }}</h1>
    <p>把散落在各平台的对话，变成看得见的成长记录。</p>

    <div class="auth-tabs">
      <button type="button" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
      <button type="button" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
    </div>

    <form @submit.prevent="submit" style="margin-top: 20px">
      <div class="field">
        <label>邮箱</label>
        <input v-model="email" type="email" required autocomplete="username" />
      </div>
      <div class="field">
        <label>密码</label>
        <input v-model="password" type="password" required minlength="8" autocomplete="current-password" />
      </div>
      <button class="btn" type="submit" :disabled="busy" style="width: 100%; margin-top: 8px">
        {{ busy ? (mode === 'register' ? '创建中…' : '进入中…') : (mode === 'register' ? '注册并进入' : '进入工作区') }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
    </form>

    <div class="tip" style="margin-top: 20px">
      {{ mode === 'register' ? '设一个至少 8 位的密码，注册好就直接进来。' : '还没有账号？点上面的「注册」，填邮箱和密码就能建好。' }}
    </div>
  </div>
</template>
