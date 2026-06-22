<template>
  <div class="resources-page">
    <div class="section-header">
      <div class="section-label">资源工坊</div>
      <h2>📚 学习资源生成</h2>
      <p>多Agent协同为您生成8类个性化学习资源</p>
    </div>

    <!-- Generation Panel -->
    <div class="card" style="margin-bottom:24px">
      <div class="grid grid-3">
        <div class="form-group">
          <label style="color:var(--text-secondary);font-size:13px">课程</label>
          <select class="input" v-model="config.course_name">
            <option v-for="c in courses" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
        <div class="form-group">
          <label style="color:var(--text-secondary);font-size:13px">主题/知识点</label>
          <input class="input" v-model="config.topic" placeholder="例如：神经网络基础" />
        </div>
        <div class="form-group">
          <label style="color:var(--text-secondary);font-size:13px">资源类型</label>
          <select class="input" v-model="config.resource_type">
            <option value="lecture_note">📝 课程讲义</option>
            <option value="ppt">📊 PPT课件</option>
            <option value="mindmap">🧠 思维导图</option>
            <option value="exercise">📝 练习题</option>
            <option value="project">💻 项目实战</option>
            <option value="study_note">📒 学习笔记</option>
            <option value="video_script">🎬 视频脚本</option>
          </select>
        </div>
      </div>
      <div class="flex gap-2 mt-4">
        <button class="btn btn-primary" @click="generateResource" :disabled="generating">
          <span v-if="generating" class="spinner" style="width:16px;height:16px;margin-right:8px"></span>
          🎯 生成资源
        </button>
        <button class="btn btn-accent" @click="generateAll" :disabled="generating">
          ⚡ 一键生成全部
        </button>
      </div>
    </div>

    <!-- Generated Content Display -->
    <div v-if="currentContent" class="card" style="margin-bottom:24px">
      <div class="flex justify-between items-center" style="margin-bottom:16px">
        <h3 style="font-size:18px">{{ currentContent.title || '生成结果' }}</h3>
        <button class="btn btn-sm btn-outline" @click="currentContent = null">✕ 关闭</button>
      </div>
      <div v-if="currentContent.mermaid_code" class="mermaid-container" style="margin-bottom:16px">
        <div v-html="renderedMermaid"></div>
      </div>
      <div class="markdown-content" v-html="renderMarkdown(
        currentContent.full_markdown || currentContent.content || JSON.stringify(currentContent, null, 2)
      )"></div>
    </div>

    <!-- Resource Type Cards -->
    <div style="margin-bottom:24px">
      <h3 style="margin-bottom:16px;font-size:18px">支持的资源类型</h3>
      <div class="grid grid-4">
        <div v-for="rtype in resourceTypes" :key="rtype.type"
          class="resource-card" @click="config.resource_type = rtype.type"
          :class="{ active: config.resource_type === rtype.type }">
          <div class="type-icon">{{ rtype.icon }}</div>
          <div class="title">{{ rtype.name }}</div>
          <div class="meta"><span>Agent: {{ rtype.agent }}</span></div>
        </div>
      </div>
    </div>

    <!-- My Resources History -->
    <div class="card">
      <h3 style="margin-bottom:12px;font-size:18px">我的生成历史</h3>
      <div v-if="myResources.length === 0" class="text-sm text-muted">暂无生成记录</div>
      <div v-else class="resource-list">
        <div v-for="r in myResources" :key="r.id" class="resource-item">
          <span class="badge" :class="'badge-' + (typeBadgeClass(r.resource_type))">
            {{ r.resource_type }}
          </span>
          <span class="text-sm" style="flex:1;font-weight:500">{{ r.title }}</span>
          <span class="text-xs text-muted">{{ r.course_name }} · {{ r.difficulty }}</span>
          <span class="text-xs text-muted">{{ formatDate(r.created_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { resourcesAPI } from '../api'
import { renderChatMessage } from '../composables/useContentRenderer'
import { useTheme } from '../composables/useTheme.js'
import { renderMermaidSvg } from '../utils/mermaidRuntime.js'
import dayjs from 'dayjs'

const courses = ['人工智能', '机器学习', '深度学习', '数据结构', '操作系统', '计算机网络', '大模型应用开发']

const resourceTypes = [
  { type: 'lecture_note', name: '课程讲义', icon: '📝', agent: 'PPTGenerator' },
  { type: 'ppt', name: 'PPT课件', icon: '📊', agent: 'PPTGenerator' },
  { type: 'mindmap', name: '思维导图', icon: '🧠', agent: 'MindMapGenerator' },
  { type: 'exercise', name: '练习题', icon: '✏️', agent: 'QuestionGenerator' },
  { type: 'project', name: '项目实战', icon: '💻', agent: 'CodingPractice' },
  { type: 'study_note', name: '学习笔记', icon: '📒', agent: 'PPTGenerator' },
  { type: 'video_script', name: '视频脚本', icon: '🎬', agent: 'VideoScript' },
  { type: 'animation_script', name: '动画脚本', icon: '🎨', agent: 'VideoScript' },
]

const config = ref({ course_name: '人工智能', topic: '机器学习基础', resource_type: 'lecture_note' })
const generating = ref(false)
const currentContent = ref(null)
const renderedMermaid = ref('')
const currentMermaidSource = ref('')
const myResources = ref([])
const { theme } = useTheme()

function renderMarkdown(text) { return renderChatMessage(text) }
function formatDate(date) { return dayjs(date).format('MM-DD HH:mm') }
function typeBadgeClass(type) {
  if (type === 'exercise' || type === 'project') return 'warning'
  if (type === 'video_script' || type === 'animation_script') return 'accent'
  return 'primary'
}

async function generateResource() {
  generating.value = true
  try {
    const res = await resourcesAPI.generate(config.value)
    if (res.success) {
      currentContent.value = res.data.content
      currentMermaidSource.value = res.data.content?.mermaid_code || ''
      await renderCurrentMermaid()
      await loadMyResources()
    }
  } catch (e) { console.error(e) }
  generating.value = false
}

async function generateAll() {
  generating.value = true
  try {
    const res = await resourcesAPI.generateAll({
      course_name: config.value.course_name, topic: config.value.topic, difficulty: 'basic',
    })
    if (res.success) {
      currentContent.value = { title: '全部资源已生成', content: JSON.stringify(res.data.results, null, 2) }
      currentMermaidSource.value = ''
      renderedMermaid.value = ''
      await loadMyResources()
    }
  } catch (e) { console.error(e) }
  generating.value = false
}

async function loadMyResources() {
  try {
    const res = await resourcesAPI.getMyResources()
    if (res.success) myResources.value = res.data || []
  } catch (e) { /* ignore */ }
}

async function renderCurrentMermaid() {
  if (!currentMermaidSource.value) {
    renderedMermaid.value = ''
    return
  }

  try {
    renderedMermaid.value = await renderMermaidSvg({
      source: currentMermaidSource.value,
      id: 'resource-mermaid',
      isLight: theme.value === 'light',
    })
  } catch (e) {
    renderedMermaid.value = ''
  }
}

watch(theme, () => {
  if (currentMermaidSource.value) renderCurrentMermaid()
})

onMounted(() => { loadMyResources() })
</script>

<style scoped>
.resource-card.active {
  border-color: var(--primary) !important;
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}
.resource-list { display: flex; flex-direction: column; gap: 8px; }
.resource-item {
  display: flex; gap: 12px; align-items: center;
  padding: 12px 14px; background: var(--bg-input);
  border-radius: var(--radius-sm); transition: all 0.2s;
}
.resource-item:hover { background: var(--primary-alpha); }
</style>
