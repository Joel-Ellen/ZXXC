<template>
  <div class="evaluation-page">
    <div class="section-header">
      <div class="section-label">数据洞察</div>
      <h2>📊 学习效果评估</h2>
      <p>数据驱动的学习分析，精准定位薄弱环节</p>
    </div>

    <!-- Report Generation -->
    <div class="card" style="margin-bottom:24px">
      <div class="flex gap-4 items-center" style="flex-wrap:wrap">
        <div class="form-group" style="flex:1;max-width:300px;min-width:200px">
          <label class="text-sm" style="color:var(--text-secondary)">课程</label>
          <select class="input" v-model="evalConfig.course_name">
            <option v-for="c in courses" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
        <div class="form-group" style="flex:1;max-width:200px;min-width:150px">
          <label class="text-sm" style="color:var(--text-secondary)">评估周期 (天)</label>
          <input class="input" v-model.number="evalConfig.period_days" type="number" min="7" max="365" />
        </div>
        <button class="btn btn-primary" @click="generateReport" :disabled="evaluating" style="margin-top:20px">
          <span v-if="evaluating" class="spinner" style="width:16px;height:16px;margin-right:8px"></span>
          📊 生成评估报告
        </button>
      </div>
    </div>

    <!-- Report Display -->
    <div v-if="report">
      <!-- Radar Chart -->
      <div class="card" style="margin-bottom:24px" v-if="report.radar_chart_data">
        <h3 style="margin-bottom:16px;font-size:18px">📈 能力雷达图</h3>
        <div ref="radarChart" style="height:350px"></div>
      </div>

      <!-- Metrics Cards -->
      <div class="grid grid-4" style="margin-bottom:24px" v-if="report.metrics">
        <div class="card metric-item">
          <span class="metric-icon">⏱️</span>
          <span class="metric-num">{{ report.metrics.study_hours?.toFixed(1) || 0 }}h</span>
          <span class="metric-label">学习时长</span>
        </div>
        <div class="card metric-item">
          <span class="metric-icon">✅</span>
          <span class="metric-num">{{ report.metrics.tasks_completed || 0 }}/{{ report.metrics.total_tasks || 0 }}</span>
          <span class="metric-label">完成任务</span>
        </div>
        <div class="card metric-item">
          <span class="metric-icon">📝</span>
          <span class="metric-num">{{ report.metrics.quiz_avg_score?.toFixed(1) || 0 }}分</span>
          <span class="metric-label">平均得分</span>
        </div>
        <div class="card metric-item">
          <span class="metric-icon">📚</span>
          <span class="metric-num">{{ (report.metrics.knowledge_coverage * 100)?.toFixed(0) || 0 }}%</span>
          <span class="metric-label">知识覆盖</span>
        </div>
      </div>

      <!-- Strengths & Weaknesses -->
      <div class="grid grid-2" style="margin-bottom:24px">
        <div class="card">
          <h4 style="color:var(--success);margin-bottom:12px;font-size:16px">✅ 优势领域</h4>
          <div v-for="s in report.strengths?.slice(0, 5)" :key="s.area" class="strength-item">
            <div class="flex justify-between">
              <span class="text-sm" style="font-weight:500">{{ s.area }}</span>
              <span class="badge badge-success">{{ s.score }}分</span>
            </div>
            <div class="text-xs text-muted mt-2">{{ s.evidence }}</div>
          </div>
        </div>
        <div class="card">
          <h4 style="color:var(--error);margin-bottom:12px;font-size:16px">⚠️ 薄弱环节</h4>
          <div v-for="w in report.weak_areas?.slice(0, 5)" :key="w.knowledge_point" class="weak-item">
            <div class="flex justify-between">
              <span class="text-sm" style="font-weight:500">{{ w.knowledge_point }}</span>
              <span class="badge badge-danger">{{ (w.error_rate * 100).toFixed(0) }}%</span>
            </div>
            <div class="text-xs text-muted mt-2">{{ w.suggested_focus }}</div>
          </div>
        </div>
      </div>

      <!-- Suggestions -->
      <div class="card" style="margin-bottom:24px" v-if="report.suggestions?.length">
        <h4 style="margin-bottom:16px;font-size:16px">💡 改进建议</h4>
        <div class="suggestion-list">
          <div v-for="(s, idx) in report.suggestions" :key="idx" class="suggestion-item">
            <span class="badge" :class="'badge-' + (s.priority === 'high' ? 'danger' : s.priority === 'medium' ? 'warning' : 'primary')" style="flex-shrink:0">
              {{ s.priority === 'high' ? '紧急' : s.priority === 'medium' ? '建议' : '可选' }}
            </span>
            <div>
              <div class="text-sm" style="font-weight:500">{{ s.suggestion }}</div>
              <div class="text-xs text-muted mt-1">{{ s.expected_impact }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Next Plan -->
      <div class="card" v-if="report.next_stage_plan">
        <h4 style="margin-bottom:12px;font-size:16px">🎯 下一阶段计划</h4>
        <div class="text-sm" style="margin-bottom:10px;color:var(--text-secondary)">{{ report.next_stage_plan.next_focus }}</div>
        <div class="flex gap-2" style="flex-wrap:wrap;margin-bottom:10px">
          <span v-for="a in report.next_stage_plan.recommended_actions" :key="a" class="tag">{{ a }}</span>
        </div>
        <div class="text-xs text-muted">预计需要 {{ report.next_stage_plan.estimated_weeks }} 周</div>
      </div>

      <!-- Full Report Markdown -->
      <div class="card" v-if="report.report_content">
        <h4 style="margin-bottom:12px;font-size:16px">📋 完整评估报告</h4>
        <div class="markdown-content" v-html="renderMarkdown(report.report_content)"></div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-if="!report && !evaluating" class="empty-state">
      <span class="icon">📊</span>
      <span class="title">尚未生成评估报告</span>
      <span class="desc">完成一些学习任务后，生成您的专属评估报告</span>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { evaluationAPI } from '../api'
import { marked } from 'marked'
import * as echarts from 'echarts'

const courses = ['人工智能', '机器学习', '深度学习', '数据结构', '操作系统', '计算机网络', '大模型应用开发']

const evalConfig = ref({ course_name: '人工智能', period_days: 30 })
const evaluating = ref(false)
const report = ref(null)
const radarChart = ref(null)

function renderMarkdown(text) { if (!text) return ''; try { return marked(text) } catch (e) { return text } }

async function generateReport() {
  evaluating.value = true
  try {
    const res = await evaluationAPI.generateReport(evalConfig.value)
    if (res.success && res.data?.report) {
      report.value = res.data.report
      await nextTick()
      renderRadarChart()
    }
  } catch (e) { console.error('Failed to generate report:', e) }
  evaluating.value = false
}

function renderRadarChart() {
  if (!radarChart.value || !report.value?.radar_chart_data) return
  const chart = echarts.init(radarChart.value)
  const data = report.value.radar_chart_data
  chart.setOption({
    radar: {
      indicator: data.labels.map(l => ({ name: l, max: 100 })),
      shape: 'polygon',
      splitArea: { areaStyle: { color: ['rgba(124,179,66,0.05)', 'rgba(124,179,66,0.1)'] } },
      axisName: { color: '#616161' },
    },
    series: [{
      type: 'radar',
      data: [{ value: data.scores, name: '能力评估', areaStyle: { color: 'rgba(124,179,66,0.25)' } }],
      itemStyle: { color: '#7CB342' },
      lineStyle: { color: '#7CB342', width: 2 },
    }],
  })
  window.addEventListener('resize', () => chart.resize())
}
</script>

<style scoped>
.metric-item {
  text-align: center; padding: 20px;
}
.metric-icon { font-size: 28px; display: block; margin-bottom: 8px; }
.metric-num { font-size: 24px; font-weight: 700; color: var(--primary); display: block; margin-bottom: 4px; }
.metric-label { font-size: 12px; color: var(--text-muted); }

.suggestion-list { display: flex; flex-direction: column; gap: 12px; }
.suggestion-item {
  display: flex; gap: 12px; align-items: flex-start;
  padding: 12px; background: var(--bg-input); border-radius: var(--radius-sm);
}

.strength-item, .weak-item {
  padding: 10px 0; border-bottom: 1px solid var(--border-light);
}
.strength-item:last-child, .weak-item:last-child { border-bottom: none; }
</style>
