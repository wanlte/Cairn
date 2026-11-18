import { reactive, computed } from 'vue'
import { api } from '../api/client'
import type { TokenResponse } from '../types'

const state = reactive({
  token: localStorage.getItem('cairn_token') || '',
  email: localStorage.getItem('cairn_email') || '',
})

function persist(email: string, tokens: TokenResponse): void {
  state.token = tokens.access_token
  state.email = email
  localStorage.setItem('cairn_token', tokens.access_token)
  localStorage.setItem('cairn_email', email)
}

export const auth = {
  state,
  isLoggedIn: computed(() => Boolean(state.token)),

  async register(email: string, password: string): Promise<void> {
    await api.post('/auth/register', { email, password })
    const tokens = await api.post<TokenResponse>('/auth/login', { email, password })
    persist(email, tokens)
  },

  async login(email: string, password: string): Promise<void> {
    const tokens = await api.post<TokenResponse>('/auth/login', { email, password })
    persist(email, tokens)
  },

  logout(): void {
    state.token = ''
    state.email = ''
    localStorage.removeItem('cairn_token')
    localStorage.removeItem('cairn_email')
  },
}
