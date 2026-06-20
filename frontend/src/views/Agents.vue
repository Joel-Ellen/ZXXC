<template>
  <div class="agents-page">
    <div class="section-header">
      <div class="section-label">系统监控</div>
      <h2>🤖 多智能体监控</h2>
      <p>实时查看10个Agent的运行状态和协同工作流程</p>
    </div>

    <!-- Orchestrator Status -->
    <div class="card" style="margin-bottom:24px">
      <div class="flex justify-between items-center" style="flex-wrap:wrap;gap:12px">
        <div>
          <h3 style="font-size:18px">编排器状态</h3>
          <div class="text-sm text-muted mt-2">
            {{ orchStatus?.total_agents || 0 }} 个Agent |
            {{ orchStatus?.active_agents || 0 }} 个活跃 |
            {{ orchStatus?.idle_agents || 0 }} 个待命
          </div>
        </div>
        <div>
          <span class="badge" :class="orchStatus?.active_agents > 0 ? 'badge-accent' : 'badge-success'">
            {{ orchStatus?.active_agents > 0 ? '工作中' : '空闲' }}
          </span>
        </div>
      </div>
      <div class="flex gap-2 mt-4">
        <button class="btn btn-sm btn-outline" @click="refreshStatus">🔄 刷新</button>
        <button class="btn btn-sm btn-outline" @click="autoRefresh = !autoRefresh">
          {{ autoRefresh ? '⏸️ 停止' : '▶️ 自动刷新' }}
        </button>
      </div>
    </div>

    <!-- Agent Status Grid -->
    <div class="grid grid-2" style="margin-bottom:24px">
      <div v-for="agent in agents" :key="agent.agent_name" class="agent-card">
        <div class="agent-status-icon" :class="agent.status"></div>
        <div class="agent-info">
          <div class="agent-name">{{ agent.agent_name }}</div>
          <div class="agent-task" v-if="agent.current_task">{{ agent.current_task }}</div>
        </div>
        <div class="agent-metrics">
          <div class="progress-bar" style="width:80px" v-if="agent.status === 'working'">
            <div class="fill" :style="{ width: agent.progress + '%' }"></div>
          </div>
          <span class="badge" :class="statusBadgeClass(agent.status)">{{ statusLabel(agent.status) }}</span>
          <span class="text-xs text-muted">{{ agent.tokens_used }} tokens</span>
        </div>
      </div>
    </div>

    <!-- Agent Workflow Diagram -->
    <div class="card" style="margin-bottom:24px">
      <h3 style="margin-bottom:16px;font-size:18px">🔄 Agent协同工作流程图</h3>
      <div class="mermaid-container" v-html="workflowDiagram"></div>
    </div>

    <!-- Agent Description Cards -->
    <h3 style="margin-bottom:16px;font-size:18px">Agent 能力概览</h3>
    <div class="grid grid-3">
      <div v-for="desc in agentDescriptions" :key="desc.name" class="card agent-desc-card">
        <h4 style="font-size:16px;margin-bottom:8px">{{ desc.icon }} {{ desc.name }}</h4>
        <div class="text-sm text-muted mb-4">{{ desc.role }}</div>
        <div class="text-xs text-muted" style="line-height:1.6;margin-bottom:12px">{{ desc.description }}</div>
        <div class="flex gap-2" style="flex-wrap:wrap">
          <span v-for="dep in desc.dependsOn" :key="dep" class="badge badge-primary">{{ dep }}</span>
          <span v-if="!desc.dependsOn.length" class="badge badge-success">独立运行</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { agentsAPI } from '../api'
import mermaid from 'mermaid'

const agents = ref([])
const orchStatus = ref(null)
const workflowDiagram = ref('')
const autoRefresh = ref(true)
let refreshTimer = null

const agentDescriptions = [
  { name: 'StudentProfiler', icon: '👤', role: '学生画像构建', description: '通过对话自动构建8维学习画像', dependsOn: [] },
  { name: 'KnowledgeAnalysis', icon: '🧩', role: '知识点拆解', description: '课程知识体系分析与知识点依赖建模', dependsOn: ['StudentProfiler'] },
  { name: 'ResourcePlanner', icon: '📋', role: '学习资源规划', description: '5阶段学习路径与周计划生成', dependsOn: ['StudentProfiler', 'KnowledgeAnalysis'] },
  { name: 'PPTGenerator', icon: '📊', role: '课件生成', description: '结构化PPT课件与讲义生成', dependsOn: ['ResourcePlanner'] },
  { name: 'QuestionGenerator', icon: '✏️', role: '题库生成', description: '4类题型个性化习题生成', dependsOn: ['ResourcePlanner'] },
  { name: 'MindMapGenerator', icon: '🧠', role: '思维导图生成', description: 'Mermaid格式知识可视化导图', dependsOn: ['ResourcePlanner'] },
  { name: 'CodingPractice', icon: '💻', role: '代码实战生成', description: '编程练习与项目案例生成', dependsOn: ['ResourcePlanner'] },
  { name: 'VideoScript', icon: '🎬', role: '视频脚本生成', description: '教学视频与动画讲解文案', dependsOn: ['ResourcePlanner'] },
  { name: 'LearningCoach', icon: '🎓', role: '学习指导', description: '苏格拉底式智能辅导与代码调试', dependsOn: ['StudentProfiler', 'KnowledgeAnalysis'] },
  { name: 'Evaluation', icon: '📊', role: '学习评估', description: '数据驱动的6维学习效果分析', dependsOn: ['StudentProfiler', 'LearningCoach'] },
]

function statusLabel(status) {
  const map = { idle: '待命', working: '工作中', completed: '完成', error: '异常' }
  return map[status] || status
}
function statusBadgeClass(status) {
  const map = { idle: 'badge-primary', working: 'badge-accent', completed: 'badge-success', error: 'badge-danger' }
  return map[status] || 'badge-primary'
}

async function refreshStatus() {
  try {
    const res = await agentsAPI.getStatus()
    if (res.success && res.data) {
      agents.value = res.data.agents || []
      orchStatus.value = res.data.orchestrator || {}
      if (res.data.workflow_diagram) {
        const code = res.data.workflow_diagram.replace('```mermaid', '').replace('```', '').trim()
        try { const { svg } = await mermaid.render('agent-workflow-svg', code); workflowDiagram.value = svg } catch (e) { /* ignore */ }
      }
    }
  } catch (e) { console.error('Failed to refresh agent status:', e) }
}

onMounted(() => {
  mermaid.initialize({ startOnLoad: false, theme: 'default' })
  refreshStatus()
  refreshTimer = setInterval(() => { if (autoRefresh.value) refreshStatus() }, 3000)
})
onUnmounted(() => { if (refreshTimer) clearInterval(refreshTimer) })
</script>

<style scoped>
.agent-desc-card { padding: 20px; }
.agent-desc-card:hover { transform: translateY(-4px); }
.agent-metrics {
  display: flex; flex-direction: column;
  align-items: flex-end; gap: 4px;
  min-width: 100px;
}
</style>
