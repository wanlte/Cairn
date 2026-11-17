import { reactive, computed } from 'vue'
import { api } from '../api/client'
import type { TokenResponse } from '../types'

const state = reactive({
  token: localStorage.getItem('cairn_token') || '',
  email: localStorage.getItem('cairn_email') || '',
})

export const auth = {
  state,
  isLoggedIn: computed(() => Boolean(state.token)),

  async login(email: string, password: string): Promise<void> {
    await api.post('/auth/register', { email, password }).catch(() => undefined)
    const tokens = await api.post<TokenResponse>('/auth/login', { email, password })
    state.token = tokens.access_token
    state.email = email
    localStorage.setItem('cairn_token', tokens.access_token)
    localStorage.setItem('cairn_email', email)
  },

  logout(): void {
    state.token = ''
    state.email = ''
    localStorage.removeItem('cairn_token')
    localStorage.removeItem('cairn_email')
  },
}
