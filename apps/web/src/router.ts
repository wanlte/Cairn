import { createRouter, createWebHistory } from 'vue-router'
import { auth } from './stores/auth'
import HomeView from './views/HomeView.vue'
import ProfileView from './views/ProfileView.vue'
import LoginView from './views/LoginView.vue'
import ReviewReportView from './views/ReviewReportView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    { path: '/', name: 'home', component: HomeView, meta: { requiresAuth: true } },
    { path: '/profile', name: 'profile', component: ProfileView, meta: { requiresAuth: true } },
    { path: '/reports', name: 'reports', component: ReviewReportView, meta: { requiresAuth: true } },
    {
      path: '/reports/:id',
      name: 'report-detail',
      component: ReviewReportView,
      meta: { requiresAuth: true },
    },
    { path: '/import', redirect: '/' },
    { path: '/review', redirect: '/reports' },
    { path: '/chat', redirect: '/' },
    { path: '/settings', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !auth.isLoggedIn.value) {
    return { name: 'login' }
  }
  if (to.name === 'login' && auth.isLoggedIn.value) {
    return { name: 'home' }
  }
  return true
})
