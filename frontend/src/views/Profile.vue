<template>
  <div class="profile-page">
    <div class="section-header">
      <div class="section-label">核心功能</div>
      <h2>🎯 学习画像构建</h2>
      <p>通过对话方式自动构建您的学习画像，无需填写问卷</p>
    </div>

    <div class="grid grid-2" style="margin-bottom:24px">
      <!-- Chat Panel -->
      <div class="card chat-panel">
        <div class="chat-messages" ref="chatContainer">
          <div v-if="messages.length === 0" class="empty-state">
            <span class="icon">💬</span>
            <span class="title">开始对话，构建您的学习画像</span>
            <span class="desc">AI会通过自然对话了解您的学习背景、目标和偏好</span>
          </div>
          <div v-for="(msg, idx) in messages" :key="idx"
            class="chat-message" :class="msg.role">
            <div class="msg-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
            <div class="msg-bubble markdown-content" v-html="renderMarkdown(msg.content)"></div>
          </div>
          <div v-if="processing" class="chat-message assistant">
            <div class="msg-avatar">🤖</div>
            <div class="msg-bubble">
              <div class="typing-indicator"><span></span><span></span><span></span></div>
            </div>
          </div>
        </div>
        <div class="chat-input-area">
          <textarea class="input" v-model="inputMessage" placeholder="分享您的学习情况..."
            @keydown.enter.exact.prevent="sendMessage" :disabled="processing" rows="2"></textarea>
          <button class="btn btn-primary send-btn" @click="sendMessage" :disabled="processing || !inputMessage.trim()">
            ➤
          </button>
        </div>
      </div>

      <!-- Profile Display -->
      <div class="card">
        <h3 style="margin-bottom:16px">📋 学习画像
          <span class="badge badge-info" style="margin-left:8px" v-if="profile">
            v{{ profile.profile_version }}
          </span>
        </h3>

        <div v-if="!profile" class="empty-state">
          <span class="icon">📝</span>
          <span class="title">画像尚未构建</span>
          <span class="desc">请通过左侧对话与AI交流，自动生成画像</span>
        </div>

        <div v-else class="profile-details">
          <!-- Basic Info -->
          <div class="profile-section">
            <h4>基本信息</h4>
            <div class="info-grid">
              <div class="info-item"><span class="label">专业</span><span class="value">{{ profile.major || '未知' }}</span></div>
              <div class="info-item"><span class="label">年级</span><span class="value">{{ profile.grade || '未知' }}</span></div>
              <div class="info-item"><span class="label">学习目标</span><span class="value">{{ profile.learning_goal || '未设定' }}</span></div>
              <div class="info-item"><span class="label">周学习时长</span><span class="value">{{ profile.weekly_study_hours || 0 }}h</span></div>
            </div>
          </div>

          <!-- Dimensions -->
          <div class="profile-section" v-if="profile.dimensions">
            <h4>画像维度</h4>
            <div class="dimension-list">
              <div v-for="(dim, key) in profile.dimensions" :key="key"
                class="dimension-item" v-if="dim">
                <div class="flex justify-between items-center">
                  <span class="dim-label">{{ dimNames[key] || key }}</span>
                  <span class="badge" :class="dim.confidence > 0.7 ? 'badge-success' : 'badge-warning'">
                    {{ (dim.confidence * 100).toFixed(0) }}%
                  </span>
                </div>
                <div class="progress-bar mt-2">
                  <div class="fill" :style="{ width: dim.score + '%' }"></div>
                </div>
                <div class="text-xs text-muted mt-2">{{ dim.description }}</div>
              </div>
            </div>
          </div>

          <!-- Mastered Knowledge -->
          <div class="profile-section" v-if="profile.mastered_knowledge?.length">
            <h4>已掌握知识</h4>
            <div class="flex gap-2" style="flex-wrap:wrap">
              <span v-for="k in profile.mastered_knowledge" :key="k" class="badge badge-success">{{ k }}</span>
            </div>
          </div>

          <div class="text-xs text-muted">
            置信度：{{ (profile.confidence_score * 100).toFixed(0) }}% |
            更新于：{{ formatDate(profile.last_updated) }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { profileAPI } from '../api'
import { useUserStore } from '../stores/user'
import { renderChatMessage } from '../composables/useContentRenderer'
import dayjs from 'dayjs'

const userStore = useUserStore()
const messages = ref([])
const inputMessage = ref('')
const processing = ref(false)
const profile = ref(null)
const chatContainer = ref(null)
const sessionId = crypto.randomUUID()

const dimNames = {
  major_background: '专业背景', knowledge_level: '知识基础',
  learning_ability: '学习能力', learning_preference: '学习偏好',
  cognitive_style: '认知风格', weak_points: '薄弱环节',
  interest_direction: '兴趣方向', career_goal: '职业目标',
}

function renderMarkdown(text) { return renderChatMessage(text) }
function formatDate(date) { return dayjs(date).format('YYYY-MM-DD HH:mm') }

async function sendMessage() {
  const text = inputMessage.value.trim()
  if (!text || processing.value) return

  // Auth guard — prevent unauthenticated API calls
  if (!userStore.isAuthenticated) {
    messages.value.push({ role: 'assistant', content: '⚠️ 请先登录后再使用画像构建功能。' })
    return
  }

  messages.value.push({ role: 'user', content: text })
  inputMessage.value = ''
  processing.value = true
  await nextTick(); scrollToBottom()
  try {
    const res = await profileAPI.build(text, sessionId)
    if (res.success && res.data) {
      const data = res.data
      // ── New standardized format ──
      const responseText = data.summary_markdown || data.next_question || '画像已更新！'
      messages.value.push({ role: 'assistant', content: responseText })
      if (data.profile_update?.dimensions) {
        profile.value = {
          major: data.profile_update.major, grade: data.profile_update.grade,
          university: data.profile_update.university, learning_goal: data.profile_update.learning_goal,
          weekly_study_hours: data.profile_update.weekly_study_hours,
          dimensions: data.profile_update.dimensions,
          mastered_knowledge: data.profile_update.mastered_knowledge,
          profile_version: data.profile_update.profile_version || 1,
          confidence_score: data.profile_update.confidence_score || 0.5,
          last_updated: new Date().toISOString(),
        }
      }
    }
  } catch (e) {
    const msg = e.response?.status === 401
      ? '登录已过期，请刷新页面重新登录。'
      : '抱歉，处理出现错误，请重试。'
    messages.value.push({ role: 'assistant', content: msg })
  }
  processing.value = false
  await nextTick(); scrollToBottom()
}

function scrollToBottom() {
  if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight
}

async function loadProfile() {
  try {
    const res = await profileAPI.getMyProfile()
    if (res.success && res.data) profile.value = res.data
  } catch (e) { console.error('Failed to load profile:', e) }
}

onMounted(() => { if (userStore.isAuthenticated) loadProfile() })
</script>

<style scoped>
.chat-panel { display: flex; flex-direction: column; height: 600px; }
.chat-messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.chat-input-area { display: flex; gap: 8px; padding: 12px; border-top: 1px solid var(--border-light); }
.chat-input-area textarea { flex: 1; min-height: 44px; }
.send-btn { height: 44px; width: 44px; border-radius: 50%; padding: 0; font-size: 18px; }

.profile-details { display: flex; flex-direction: column; gap: 20px; }
.profile-section h4 {
  font-size: 13px; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;
}
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.info-item {
  padding: 10px 14px; background: var(--bg-input);
  border-radius: var(--radius-sm);
}
.info-item .label { font-size: 11px; color: var(--text-muted); display: block; }
.info-item .value { font-size: 14px; color: var(--text-primary); font-weight: 500; }

.dimension-list { display: flex; flex-direction: column; gap: 14px; }
.dim-label { font-size: 13px; color: var(--text-secondary); font-weight: 500; }
</style>
