<template>
  <div class="app-container">
    <!-- Sidebar Navigation -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <div class="logo" @click="$router.push('/')" style="cursor:pointer">
          <span class="logo-icon">🌟</span>
          <span class="logo-text" v-show="!sidebarCollapsed">
            <span style="display:flex;flex-direction:column">
              <span style="font-size:17px;font-weight:700;color:var(--primary);line-height:1.2">智学星辰</span>
              <span style="font-size:10px;color:var(--text-muted);letter-spacing:0.5px">AI学习助手</span>
            </span>
          </span>
        </div>
        <button class="collapse-btn" @click="sidebarCollapsed = !sidebarCollapsed">
          {{ sidebarCollapsed ? '▶' : '◀' }}
        </button>
      </div>
      <nav class="sidebar-nav">
        <router-link to="/" class="nav-item" :class="{ active: $route.path === '/' }">
          <span class="nav-icon">🏠</span>
          <span class="nav-text" v-show="!sidebarCollapsed">首页</span>
        </router-link>
        <router-link to="/profile" class="nav-item" :class="{ active: $route.path === '/profile' }">
          <span class="nav-icon">👤</span>
          <span class="nav-text" v-show="!sidebarCollapsed">学习画像</span>
        </router-link>
        <router-link to="/learning-path" class="nav-item" :class="{ active: $route.path === '/learning-path' }">
          <span class="nav-icon">🗺️</span>
          <span class="nav-text" v-show="!sidebarCollapsed">学习路径</span>
        </router-link>
        <router-link to="/resources" class="nav-item" :class="{ active: $route.path === '/resources' }">
          <span class="nav-icon">📚</span>
          <span class="nav-text" v-show="!sidebarCollapsed">学习资源</span>
        </router-link>
        <router-link to="/tutor" class="nav-item" :class="{ active: $route.path === '/tutor' }">
          <span class="nav-icon">🎓</span>
          <span class="nav-text" v-show="!sidebarCollapsed">智能辅导</span>
        </router-link>
        <router-link to="/evaluation" class="nav-item" :class="{ active: $route.path === '/evaluation' }">
          <span class="nav-icon">📊</span>
          <span class="nav-text" v-show="!sidebarCollapsed">学习评估</span>
        </router-link>
        <router-link to="/agents" class="nav-item" :class="{ active: $route.path === '/agents' }">
          <span class="nav-icon">🤖</span>
          <span class="nav-text" v-show="!sidebarCollapsed">Agent状态</span>
        </router-link>
      </nav>
      <div class="sidebar-footer" v-show="!sidebarCollapsed">
        <div class="user-info" v-if="userStore.user">
          <span class="avatar">👤</span>
          <span class="username">{{ userStore.user.username }}</span>
        </div>
        <button v-if="userStore.user" class="logout-btn" @click="handleLogout">退出登录</button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="main-content">
      <!-- Top bar -->
      <header class="topbar">
        <div class="topbar-left">
          <h1 class="page-title">{{ pageTitle }}</h1>
        </div>
        <div class="topbar-right">
          <div class="agent-indicator" v-if="activeAgentCount > 0">
            <span class="pulse"></span>
            {{ activeAgentCount }} Agent{{ activeAgentCount > 1 ? 's' : '' }} 运行中
          </div>
          <div class="ws-status">
            {{ wsConnected ? '🟢' : '🔴' }}
          </div>
        </div>
      </header>

      <!-- Page Content -->
      <div class="page-content">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from './stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const sidebarCollapsed = ref(false)
const wsConnected = ref(false)
const activeAgentCount = ref(0)
let ws = null

const pageTitle = computed(() => {
  const titles = {
    '/': '系统首页',
    '/profile': '学习画像',
    '/learning-path': '学习路径',
    '/resources': '学习资源',
    '/tutor': '智能辅导',
    '/evaluation': '学习评估',
    '/agents': 'Agent监控',
  }
  return titles[route.path] || '智学星辰'
})

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/api/ws/agent-stream`
  ws = new WebSocket(wsUrl)
  ws.onopen = () => { wsConnected.value = true }
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'agent_status') {
      activeAgentCount.value = data.orchestrator?.active_agents || 0
    }
  }
  ws.onclose = () => { wsConnected.value = false; setTimeout(connectWebSocket, 3000) }
  ws.onerror = () => { wsConnected.value = false }
}

function handleLogout() {
  userStore.logout()
  router.push('/')
}

onMounted(() => {
  connectWebSocket()
  userStore.loadFromStorage()
})

onUnmounted(() => {
  if (ws) ws.close()
})
</script>
