import { createRouter, createWebHistory } from 'vue-router'
import { auth } from './stores/auth'
import ImportView from './views/ImportView.vue'
import ReviewView from './views/ReviewView.vue'
import ProfileView from './views/ProfileView.vue'
import ChatView from './views/ChatView.vue'
import SettingsView from './views/SettingsView.vue'
import LoginView from './views/LoginView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    { path: '/', redirect: '/import' },
    { path: '/import', name: 'import', component: ImportView, meta: { requiresAuth: true } },
    { path: '/review', name: 'review', component: ReviewView, meta: { requiresAuth: true } },
    { path: '/profile', name: 'profile', component: ProfileView, meta: { requiresAuth: true } },
    { path: '/chat', name: 'chat', component: ChatView, meta: { requiresAuth: true } },
    { path: '/settings', name: 'settings', component: SettingsView, meta: { requiresAuth: true } },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !auth.isLoggedIn.value) {
    return { name: 'login' }
  }
  if (to.name === 'login' && auth.isLoggedIn.value) {
    return { name: 'import' }
  }
  return true
})
