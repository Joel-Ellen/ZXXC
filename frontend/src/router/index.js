import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue'),
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('../views/Profile.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/learning-path',
    name: 'LearningPath',
    component: () => import('../views/LearningPath.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/resources',
    name: 'Resources',
    component: () => import('../views/Resources.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/tutor',
    name: 'Tutor',
    component: () => import('../views/Tutor.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/evaluation',
    name: 'Evaluation',
    component: () => import('../views/Evaluation.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/agents',
    name: 'Agents',
    component: () => import('../views/Agents.vue'),
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// ============================================================
// Navigation Guard — 防止未登录用户访问受保护页面
// ============================================================
router.beforeEach((to, from, next) => {
  if (to.meta.requiresAuth) {
    // Check localStorage directly (not Pinia store — avoids race condition
    // where store hasn't hydrated yet from onMounted)
    const stored = localStorage.getItem('ai_learning_user')
    if (stored) {
      try {
        const { token } = JSON.parse(stored)
        if (token) {
          return next()  // Has token → allow
        }
      } catch (e) { /* fall through to redirect */ }
    }
    // No valid token → redirect to home (login page)
    return next({ path: '/', query: { redirect: to.path } })
  }
  next()
})

export default router
