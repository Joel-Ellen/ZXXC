<template>
  <div class="learning-path-page">
    <div class="section-header">
      <div class="section-label">核心功能</div>
      <h2>🗺️ 学习路径规划</h2>
      <p>基于您的画像自动生成5阶段递进式学习路径</p>
    </div>

    <!-- Configuration -->
    <div class="card" style="margin-bottom:24px">
      <div class="grid grid-4">
        <div class="form-group">
          <label class="text-sm text-muted">课程</label>
          <select class="input" v-model="config.course_name">
            <option v-for="c in courses" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
        <div class="form-group">
          <label class="text-sm text-muted">目标水平</label>
          <select class="input" v-model="config.target_level">
            <option value="basic">基础</option>
            <option value="intermediate">进阶</option>
            <option value="advanced">高级</option>
            <option value="expert">专家</option>
          </select>
        </div>
        <div class="form-group">
          <label class="text-sm text-muted">每周学习时长 (h)</label>
          <input class="input" v-model.number="config.weekly_hours" type="number" min="1" max="40" />
        </div>
        <div class="form-group">
          <label class="text-sm text-muted">目标周期 (周)</label>
          <input class="input" v-model.number="config.duration_weeks" type="number" min="4" max="52" />
        </div>
      </div>
      <button class="btn btn-primary mt-4" @click="generatePath" :disabled="generating">
        <span v-if="generating" class="spinner" style="width:16px;height:16px;margin-right:8px"></span>
        {{ generating ? '多Agent协同生成中...' : '🚀 生成学习路径' }}
      </button>
    </div>

    <!-- Learning Path Results -->
    <div v-if="pathData" class="path-results">
      <!-- Overview Stats -->
      <div class="stats-overview" style="margin-bottom:24px">
        <div class="grid grid-4">
          <div class="card metric-card">
            <span class="metric-num">{{ pathData.plan_overview?.total_weeks || 0 }}</span>
            <span class="metric-label">总周数</span>
          </div>
          <div class="card metric-card">
            <span class="metric-num">{{ pathData.plan_overview?.weekly_hours || 0 }}h</span>
            <span class="metric-label">每周学习</span>
          </div>
          <div class="card metric-card">
            <span class="metric-num">5</span>
            <span class="metric-label">学习阶段</span>
          </div>
          <div class="card metric-card">
            <span class="metric-num">{{ pathData.plan_overview?.target_level || '-' }}</span>
            <span class="metric-label">目标水平</span>
          </div>
        </div>
      </div>

      <!-- Stage Timeline -->
      <div class="stages">
        <div v-for="(stage, idx) in pathData.stages" :key="idx" class="stage-card card">
          <div class="stage-header">
            <div class="stage-number">{{ idx + 1 }}</div>
            <div class="stage-info">
              <h4 style="font-size:18px;font-weight:600">{{ stage.stage_name }}</h4>
              <span class="text-sm text-muted">{{ stage.weeks }} · {{ stage.goals?.[0] }}</span>
            </div>
          </div>
          <div class="stage-topics mt-4">
            <span v-for="t in stage.topics?.slice(0, 8)" :key="t" class="tag">{{ t }}</span>
          </div>
          <!-- Weekly Plans (expandable) -->
          <details class="mt-4" v-if="stage.weekly_plan?.length">
            <summary class="text-sm" style="cursor:pointer;color:var(--primary);font-weight:500">
              📋 查看{{ stage.weekly_plan.length }}周详细计划
            </summary>
            <div class="weekly-plans mt-4">
              <div v-for="week in stage.weekly_plan" :key="week.week" class="week-item">
                <div class="week-header">
                  <span class="badge badge-accent">第{{ week.week }}周</span>
                  <span class="text-sm" style="font-weight:500">{{ week.focus }}</span>
                </div>
                <ul class="task-list">
                  <li v-for="(task, ti) in week.tasks?.slice(0, 5)" :key="ti" class="text-sm">
                    <span class="badge" :class="'badge-' + (task.priority === 'high' ? 'danger' : task.priority === 'medium' ? 'warning' : 'primary')" style="margin-right:6px">
                      {{ task.priority }}
                    </span>
                    {{ task.title }} ({{ task.estimated_hours }}h)
                  </li>
                </ul>
              </div>
            </div>
          </details>
        </div>
      </div>

      <!-- Personal Tips -->
      <div class="card mt-4" v-if="pathData.personalized_tips?.length">
        <h4 style="font-size:16px">💡 个性化学习建议</h4>
        <ul class="mt-2" style="padding-left:20px">
          <li v-for="tip in pathData.personalized_tips" :key="tip" class="text-sm" style="margin-bottom:6px;color:var(--text-secondary)">{{ tip }}</li>
        </ul>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="!pathData && !generating" class="empty-state">
      <span class="icon">🗺️</span>
      <span class="title">尚未生成学习路径</span>
      <span class="desc">配置参数后点击生成，多Agent协同为您规划</span>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { learningAPI } from '../api'

const courses = ['人工智能', '机器学习', '深度学习', '数据结构', '操作系统', '计算机网络', '大模型应用开发']

const config = ref({
  course_name: '人工智能', target_level: 'advanced',
  weekly_hours: 10, duration_weeks: 16,
})

const generating = ref(false)
const pathData = ref(null)

async function generatePath() {
  generating.value = true
  try {
    const res = await learningAPI.generatePath(config.value)
    if (res.success && res.data?.learning_path) pathData.value = res.data.learning_path
  } catch (e) { console.error('Failed to generate path:', e) }
  generating.value = false
}
</script>

<style scoped>
.metric-card {
  text-align: center; padding: 20px;
  background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}
.metric-num { font-size: 28px; font-weight: 700; color: var(--primary); display: block; margin-bottom: 4px; }
.metric-label { font-size: 13px; color: var(--text-muted); }

.stages { display: flex; flex-direction: column; gap: 16px; }
.stage-card { padding: 24px; }
.stage-card:hover { transform: translateY(-4px); }
.stage-header { display: flex; gap: 20px; align-items: center; }
.stage-number {
  width: 52px; height: 52px; border-radius: 50%;
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  color: white; display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 700; flex-shrink: 0;
  box-shadow: 0 4px 14px rgba(124,179,66,0.35);
}
.stage-topics { display: flex; flex-wrap: wrap; gap: 6px; }

.weekly-plans { display: flex; flex-direction: column; gap: 12px; }
.week-item { padding: 14px; background: var(--bg-input); border-radius: var(--radius-sm); }
.week-header { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.task-list { padding-left: 20px; display: flex; flex-direction: column; gap: 6px; }
</style>
