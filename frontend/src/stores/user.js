import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authAPI } from '../api'

export const useUserStore = defineStore('user', () => {
  const user = ref(null)
  const token = ref(null)
  const isAuthenticated = computed(() => !!token.value && !!user.value)

  function loadFromStorage() {
    const stored = localStorage.getItem('ai_learning_user')
    if (stored) {
      try {
        const data = JSON.parse(stored)
        user.value = data.user
        token.value = data.token
      } catch (e) {
        localStorage.removeItem('ai_learning_user')
      }
    }
  }

  function saveToStorage() {
    localStorage.setItem('ai_learning_user', JSON.stringify({
      user: user.value,
      token: token.value,
    }))
  }

  async function login(username, password) {
    const res = await authAPI.login(username, password)
    if (res.success) {
      user.value = res.data.user
      token.value = res.data.access_token
      saveToStorage()
    }
    return res
  }

  async function register(username, email, password) {
    const res = await authAPI.register(username, email, password)
    if (res.success) {
      user.value = res.data.user
      token.value = res.data.access_token
      saveToStorage()
    }
    return res
  }

  function logout() {
    user.value = null
    token.value = null
    localStorage.removeItem('ai_learning_user')
  }

  return { user, token, isAuthenticated, login, register, logout, loadFromStorage }
})
