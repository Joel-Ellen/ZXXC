<template>
  <div class="home-page">
    <!-- Hero Section (unauthenticated) -->
    <div class="hero" v-if="!userStore.isAuthenticated">
      <!-- Dynamic background blobs -->
      <div class="hero-bg">
        <div class="hero-blob hero-blob-1"></div>
        <div class="hero-blob hero-blob-2"></div>
        <div class="hero-blob hero-blob-3"></div>
      </div>
      <!-- Floating particles -->
      <div class="particles">
        <div class="particle" v-for="n in 6" :key="n"></div>
      </div>

      <div class="hero-content container">
        <div class="hero-text">
          <div class="hero-badge">🏆 软件杯国家级竞赛项目</div>
          <h1 class="hero-title">
            基于大模型的<br/>
            <span class="highlight">个性化资源生成与学习</span><br/>
            多智能体系统
          </h1>
          <p class="hero-desc">
            10个AI智能体协同工作，为您生成个性化学习资源、规划学习路径、提供智能辅导
          </p>
          <div class="hero-actions">
            <button class="btn btn-primary btn-lg" @click="showLogin = true">开始使用</button>
            <button class="btn btn-secondary btn-lg" @click="showRegister = true">注册账号</button>
          </div>
          <div class="hero-features">
            <span class="hero-feature">✅ 10+ AI Agent协同</span>
            <span class="hero-feature">✅ 7大课程方向</span>
            <span class="hero-feature">✅ 8类资源一键生成</span>
            <span class="hero-feature">✅ 5阶段学习路径</span>
          </div>
        </div>
      </div>

      <!-- Login/Register Modal -->
      <div class="modal-overlay" v-if="showLogin || showRegister" @click.self="closeModals">
        <div class="modal">
          <h2>{{ showLogin ? '欢迎回来' : '创建账号' }}</h2>
          <form @submit.prevent="handleAuth">
            <div class="form-group" v-if="showRegister">
              <label>邮箱</label>
              <input class="input" v-model="authForm.email" type="email" placeholder="your@email.com" />
            </div>
            <div class="form-group">
              <label>用户名</label>
              <input class="input" v-model="authForm.username" placeholder="请输入用户名" required />
            </div>
            <div class="form-group">
              <label>密码</label>
              <input class="input" v-model="authForm.password" type="password" placeholder="请输入密码" required />
            </div>
            <div v-if="errorMsg" class="text-sm" style="color:var(--error);margin-bottom:12px">{{ errorMsg }}</div>
            <button class="btn btn-primary w-full" type="submit" :disabled="authLoading">
              <span v-if="authLoading" class="spinner" style="width:16px;height:16px"></span>
              {{ showLogin ? '登录' : '注册' }}
            </button>
          </form>
          <p class="text-center mt-4 text-sm text-muted">
            {{ showLogin ? '没有账号？' : '已有账号？' }}
            <a href="#" @click.prevent="showLogin = !showLogin; showRegister = !showRegister; errorMsg = ''"
               style="color:var(--primary);font-weight:500">
              {{ showLogin ? '去注册' : '去登录' }}
            </a>
          </p>
        </div>
      </div>
    </div>

    <!-- Dashboard (Authenticated) -->
    <div v-else>
      <div class="section-header">
        <h2>欢迎回来，{{ userStore.user?.username }} 👋</h2>
        <p>您的个性化AI学习助手已就绪，选择课程开始学习之旅</p>
      </div>

      <!-- Stats Section (zhihuiqingchun style) -->
      <div class="stats-section">
        <div class="stats-grid container">
          <div class="stat-card">
            <div class="stat-icon">🤖</div>
            <div class="stat-value">10+</div>
            <div class="stat-label">AI Agent协同</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">📚</div>
            <div class="stat-value">8</div>
            <div class="stat-label">资源类型</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">🗺️</div>
            <div class="stat-value">5</div>
            <div class="stat-label">学习阶段</div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">🎯</div>
            <div class="stat-value">7</div>
            <div class="stat-label">课程方向</div>
          </div>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="section" style="padding:48px 0">
        <div class="section-header">
          <div class="section-label">快速入口</div>
          <h2>开始您的学习之旅</h2>
          <p>四大核心模块，覆盖完整学习流程</p>
        </div>
        <div class="grid grid-4">
          <router-link to="/profile" class="feature-card">
            <div class="feature-icon"><span style="font-size:28px">👤</span></div>
            <div class="feature-title">学习画像</div>
            <div class="feature-desc">AI对话构建您的8维学习画像，精准了解学习特点</div>
          </router-link>
          <router-link to="/learning-path" class="feature-card">
            <div class="feature-icon"><span style="font-size:28px">🗺️</span></div>
            <div class="feature-title">学习路径</div>
            <div class="feature-desc">5阶段递进式学习路线图，每周任务清晰可见</div>
          </router-link>
          <router-link to="/resources" class="feature-card">
            <div class="feature-icon"><span style="font-size:28px">📚</span></div>
            <div class="feature-title">生成资源</div>
            <div class="feature-desc">AI一键生成8类学习材料，PPT/导图/题库/代码</div>
          </router-link>
          <router-link to="/tutor" class="feature-card">
            <div class="feature-icon"><span style="font-size:28px">🎓</span></div>
            <div class="feature-title">智能辅导</div>
            <div class="feature-desc">24/7 AI导师在线，概念讲解、错题分析、代码调试</div>
          </router-link>
        </div>
      </div>

      <!-- Course Selection -->
      <div class="card" style="margin-bottom:24px">
        <h3 style="margin-bottom:16px;font-size:18px">选择课程方向</h3>
        <div class="flex gap-2" style="flex-wrap:wrap;margin-bottom:16px">
          <button v-for="course in courses" :key="course"
            class="btn" :class="selectedCourse === course ? 'btn-primary' : 'btn-outline'"
            @click="selectedCourse = course">
            {{ course }}
          </button>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-primary" @click="quickStart">🚀 快速开始学习</button>
          <button class="btn btn-accent" @click="generateAllResources">⚡ 一键生成全部资源</button>
        </div>
      </div>

      <!-- Agent Workflow Preview -->
      <div class="card">
        <h3 style="margin-bottom:12px;font-size:18px">多智能体架构预览</h3>
        <div class="mermaid-container" v-html="renderedMermaid"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'
import { agentsAPI, resourcesAPI } from '../api'
import { useTheme } from '../composables/useTheme.js'
import { renderMermaidSvg } from '../utils/mermaidRuntime.js'

const router = useRouter()
const userStore = useUserStore()
const { theme } = useTheme()

const showLogin = ref(false)
const showRegister = ref(false)
const authLoading = ref(false)
const errorMsg = ref('')
const authForm = ref({ username: '', email: '', password: '' })
const selectedCourse = ref('人工智能')
const renderedMermaid = ref('')
const workflowSource = ref('')
const courses = ['人工智能', '机器学习', '深度学习', '数据结构', '操作系统', '计算机网络', '大模型应用开发']

async function handleAuth() {
  authLoading.value = true
  errorMsg.value = ''
  try {
    let res
    if (showLogin.value) {
      res = await userStore.login(authForm.value.username, authForm.value.password)
    } else {
      res = await userStore.register(authForm.value.username, authForm.value.email, authForm.value.password)
    }
    if (!res.success) {
      errorMsg.value = res.message || '操作失败'
    } else {
      showLogin.value = false
      showRegister.value = false
    }
  } catch (e) {
    errorMsg.value = e.response?.data?.message || '网络错误'
  }
  authLoading.value = false
}

function closeModals() {
  showLogin.value = false
  showRegister.value = false
  errorMsg.value = ''
}

async function quickStart() { router.push('/profile') }

async function generateAllResources() {
  try {
    const res = await resourcesAPI.generateAll({
      course_name: selectedCourse.value,
      topic: '机器学习基础',
      difficulty: 'basic',
    })
    if (res.success) router.push('/resources')
  } catch (e) { console.error(e) }
}

async function loadWorkflowDiagram() {
  try {
    const res = await agentsAPI.getWorkflowDiagram()
    if (res.success && res.data?.mermaid) {
      workflowSource.value = res.data.mermaid
      await updateWorkflowDiagram()
    }
  } catch (e) { console.error('Failed to load workflow diagram:', e) }
}

async function updateWorkflowDiagram() {
  if (!workflowSource.value) {
    renderedMermaid.value = ''
    return
  }

  try {
    renderedMermaid.value = await renderMermaidSvg({
      source: workflowSource.value,
      id: 'workflow-svg',
      isLight: theme.value === 'light',
    })
  } catch (e) {
    console.error('Failed to render workflow diagram:', e)
    renderedMermaid.value = ''
  }
}

watch(theme, () => {
  if (workflowSource.value) updateWorkflowDiagram()
})

onMounted(() => {
  if (userStore.isAuthenticated) loadWorkflowDiagram()
})
</script>

<style scoped>
/* ============================================
   Hero Section (zhihuiqingchun style)
   ============================================ */
.hero {
  padding: 80px 0;
  background: linear-gradient(180deg, var(--bg-primary) 0%, rgba(124,179,66,0.05) 100%);
  position: relative;
  overflow: hidden;
  min-height: calc(100vh - 120px);
  display: flex;
  align-items: center;
}
.container { max-width: 1200px; margin: 0 auto; padding: 0 var(--space-lg); }

/* Dynamic background blobs */
.hero-bg {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  pointer-events: none;
  overflow: hidden;
}
.hero-blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  animation: float 8s ease-in-out infinite;
}
.hero-blob-1 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(124,179,66,0.15) 0%, transparent 70%);
  top: -100px; right: 5%;
}
.hero-blob-2 {
  width: 300px; height: 300px;
  background: radial-gradient(circle, rgba(255,179,0,0.12) 0%, transparent 70%);
  bottom: 10%; left: 5%;
  animation-delay: -4s;
}
.hero-blob-3 {
  width: 200px; height: 200px;
  background: radial-gradient(circle, rgba(41,182,246,0.1) 0%, transparent 70%);
  top: 40%; left: 15%;
  animation-delay: -2s;
}

/* Floating particles */
.particles {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  pointer-events: none;
}
.particle {
  position: absolute;
  width: 6px; height: 6px;
  background: var(--primary);
  border-radius: 50%;
  opacity: 0.4;
  animation: particleFloat 6s ease-in-out infinite;
}
.particle:nth-child(1) { left: 10%; top: 20%; }
.particle:nth-child(2) { left: 25%; top: 60%; animation-delay: 1s; background: var(--accent); }
.particle:nth-child(3) { left: 40%; top: 30%; animation-delay: 2s; }
.particle:nth-child(4) { left: 60%; top: 70%; animation-delay: 0.5s; background: var(--info); }
.particle:nth-child(5) { left: 80%; top: 40%; animation-delay: 1.5s; background: var(--accent); }
.particle:nth-child(6) { left: 15%; top: 80%; animation-delay: 2.5s; }

/* Hero content */
.hero-text {
  animation: pageSlideIn 0.8s ease-out;
  max-width: 600px;
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: var(--primary-alpha);
  border: 1px solid rgba(124,179,66,0.2);
  border-radius: var(--radius-full);
  font-size: 13px;
  font-weight: 500;
  color: var(--primary-dark);
  margin-bottom: 20px;
}
.hero-title {
  font-size: 46px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--text-primary);
  margin-bottom: 16px;
  letter-spacing: -1px;
}
.hero-title .highlight {
  background: linear-gradient(135deg, var(--primary) 0%, var(--accent) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.hero-desc {
  font-size: 17px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin-bottom: 32px;
  max-width: 520px;
}
.hero-actions {
  display: flex;
  gap: 16px;
  margin-bottom: 32px;
}
.hero-features {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
}
.hero-feature {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--text-secondary);
}

/* Secondary button (zhihuiqingchun style) */
.btn-secondary {
  background: white;
  color: var(--text-primary);
  border: 1.5px solid var(--border-medium);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 28px;
  font-size: 16px;
  font-weight: 600;
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all 0.25s ease;
}
.btn-secondary:hover {
  border-color: var(--primary);
  color: var(--primary);
  transform: translateY(-2px);
}

/* ============================================
   Stats Section (zhihuiqingchun style)
   ============================================ */
.stats-section {
  background: var(--bg-dark);
  padding: 48px 0;
  border-radius: var(--radius-xl);
  margin-bottom: 24px;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 32px;
}
.stat-card {
  text-align: center;
  padding: 20px;
  transition: all 0.3s ease;
}
.stat-card:hover { transform: translateY(-4px); }
.stat-icon {
  width: 56px; height: 56px;
  margin: 0 auto 12px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(124,179,66,0.12);
  border-radius: 14px;
  font-size: 28px;
}
.stat-value {
  font-size: 38px;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 6px;
  background: linear-gradient(135deg, var(--primary-light), var(--accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.stat-label { font-size: 14px; color: rgba(255,255,255,0.6); }

@media (max-width: 768px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}

/* ============================================
   Feature Cards (zhihuiqingchun style)
   ============================================ */
.section { padding-bottom: 0; }
.feature-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 28px 24px;
  transition: all 0.3s ease;
  text-decoration: none;
  color: var(--text-primary);
  display: block;
}
.feature-card:hover {
  border-color: var(--primary);
  box-shadow: var(--shadow-lg);
  transform: translateY(-6px);
}
.feature-icon {
  width: 56px; height: 56px;
  display: flex; align-items: center; justify-content: center;
  background: var(--primary-alpha);
  border-radius: 14px;
  margin-bottom: 16px;
  transition: all 0.3s ease;
}
.feature-card:hover .feature-icon {
  background: var(--primary);
  transform: scale(1.05);
}
.feature-card:hover .feature-icon span {
  filter: brightness(10);
}
.feature-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.feature-desc {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}
</style>
