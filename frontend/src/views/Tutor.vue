<template>
  <div class="tutor-page">
    <div class="section-header">
      <div class="section-label">AI导师</div>
      <h2>🎓 智能辅导</h2>
      <p>AI导师为您解答疑惑、分析错题、指导代码调试</p>
    </div>

    <div class="grid grid-2">
      <!-- Chat Panel -->
      <div class="card chat-panel">
        <div class="chat-messages" ref="chatContainer">
          <div v-if="chatMessages.length === 0" class="empty-state">
            <span class="icon">🎓</span>
            <span class="title">AI学习导师</span>
            <span class="desc">我可以帮您：解释概念、分析错题、调试代码、提供学习建议</span>
          </div>
          <div v-for="(msg, idx) in chatMessages" :key="idx"
            class="chat-message" :class="msg.role">
            <div class="msg-avatar">{{ msg.role === 'user' ? '👤' : '🎓' }}</div>
            <div class="msg-bubble">
              <div class="markdown-content" v-html="renderMarkdown(msg.content)"></div>
              <div v-if="msg.diagram" class="mermaid-container mt-4"><div v-html="msg.renderedDiagram"></div></div>
              <div v-if="msg.code_example" class="mt-4">
                <pre style="background:#1A1D21;padding:16px;border-radius:12px;overflow-x:auto"><code style="color:#e0e0e0;font-family:monospace">{{ msg.code_example }}</code></pre>
              </div>
            </div>
          </div>
          <div v-if="tutoring" class="chat-message assistant">
            <div class="msg-avatar">🎓</div>
            <div class="msg-bubble">
              <div class="typing-indicator"><span></span><span></span><span></span></div>
            </div>
          </div>
        </div>

        <!-- Context type selector -->
        <div class="filter-bar">
          <button v-for="ct in contextTypes" :key="ct.value"
            class="filter-chip" :class="{ active: selectedContext === ct.value }"
            @click="selectedContext = ct.value">
            {{ ct.icon }} {{ ct.label }}
          </button>
        </div>

        <div class="chat-input-area">
          <textarea class="input" v-model="question" placeholder="输入您的问题..."
            @keydown.enter.exact.prevent="askTutor" :disabled="tutoring" rows="2"></textarea>
          <button class="btn btn-primary send-btn" @click="askTutor" :disabled="tutoring || !question.trim()">➤</button>
        </div>
      </div>

      <!-- Side Panels -->
      <div>
        <!-- Quick Questions -->
        <div class="card" style="margin-bottom:16px">
          <h4 style="margin-bottom:14px;font-size:16px">💡 试试这些问题</h4>
          <div class="flex flex-col gap-2">
            <button v-for="qq in quickQuestions" :key="qq" class="btn btn-outline btn-sm" style="text-align:left"
              @click="question = qq; askTutor()">{{ qq }}</button>
          </div>
        </div>

        <!-- Code Debug Panel -->
        <div class="card">
          <h4 style="margin-bottom:14px;font-size:16px">🐛 代码调试</h4>
          <div class="form-group">
            <label style="color:var(--text-secondary);font-size:13px">粘贴您的代码</label>
            <textarea class="input" v-model="codeSnippet" rows="6"
              placeholder="粘贴需要调试的代码..." style="font-family:monospace"></textarea>
          </div>
          <div class="form-group mt-2">
            <label style="color:var(--text-secondary);font-size:13px">错误信息（可选）</label>
            <input class="input" v-model="errorMsg" placeholder="粘贴错误信息" />
          </div>
          <button class="btn btn-accent btn-sm w-full" @click="debugCode"
            :disabled="tutoring || !codeSnippet.trim()">🔍 调试分析</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { tutoringAPI } from '../api'
import { renderChatMessage } from '../composables/useContentRenderer'
import mermaid from 'mermaid'

const chatMessages = ref([])
const question = ref('')
const tutoring = ref(false)
const selectedContext = ref('concept')
const codeSnippet = ref('')
const errorMsg = ref('')
const chatContainer = ref(null)

const contextTypes = [
  { value: 'concept', label: '概念讲解', icon: '📖' },
  { value: 'problem_solving', label: '解题指导', icon: '🧩' },
  { value: 'code_debug', label: '代码调试', icon: '🐛' },
  { value: 'study_advice', label: '学习建议', icon: '💡' },
  { value: 'exam_prep', label: '备考指导', icon: '📝' },
]

const quickQuestions = [
  '什么是梯度下降算法？请用简单例子解释',
  '神经网络的激活函数有哪些？各有什么优缺点？',
  '过拟合和欠拟合有什么区别？如何解决？',
  'Python中的列表和元组有什么区别？',
  '如何理解时间复杂度和空间复杂度？',
]

function renderMarkdown(text) { return renderChatMessage(text) }

async function renderMermaidDiagram(code) {
  try { const { svg } = await mermaid.render('tutor-mermaid-' + Date.now(), code); return svg } catch (e) { return null }
}

async function askTutor() {
  const q = question.value.trim()
  if (!q || tutoring.value) return
  chatMessages.value.push({ role: 'user', content: q })
  question.value = ''
  tutoring.value = true
  await nextTick(); scrollToBottom()
  try {
    const res = await tutoringAPI.ask({
      question: q, context_type: selectedContext.value,
      code_snippet: codeSnippet.value, error_message: errorMsg.value,
    })
    if (res.success && res.data?.tutoring_result) {
      const result = res.data.tutoring_result
      let content = result.answer || result.response || result.core_definition || ''
      if (result.detailed_explanation) content += '\n\n' + result.detailed_explanation
      if (result.analogy) content += '\n\n**💡 类比理解：**' + result.analogy
      if (result.hints?.length) content += '\n\n**提示：**\n' + result.hints.map(h => '- ' + h).join('\n')
      const msg = {
        role: 'assistant', content,
        code_example: result.code_example || result.improved_code_snippet || null,
        diagram: result.diagram || null,
      }
      if (msg.diagram) msg.renderedDiagram = await renderMermaidDiagram(msg.diagram)
      chatMessages.value.push(msg)
    }
  } catch (e) { chatMessages.value.push({ role: 'assistant', content: '抱歉，辅导服务暂时不可用，请稍后再试。' }) }
  tutoring.value = false; codeSnippet.value = ''; errorMsg.value = ''
  await nextTick(); scrollToBottom()
}

async function debugCode() { selectedContext.value = 'code_debug'; question.value = '请帮我调试这段代码'; await askTutor() }

function scrollToBottom() { if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight }
</script>

<style scoped>
.chat-panel { display: flex; flex-direction: column; height: 650px; }
.chat-messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.chat-input-area { display: flex; gap: 8px; padding: 12px; border-top: 1px solid var(--border-light); }
.chat-input-area textarea { flex: 1; min-height: 44px; }
.send-btn { height: 44px; width: 44px; border-radius: 50%; padding: 0; font-size: 18px; }

/* Filter chips (zhihuiqingchun style) */
.filter-bar { display: flex; gap: 6px; padding: 8px 12px; flex-wrap: wrap; }
.filter-chip {
  padding: 6px 14px; font-size: 12px; font-weight: 500;
  color: var(--text-secondary); background: var(--bg-input);
  border: 1.5px solid var(--border-medium); border-radius: var(--radius-full);
  cursor: pointer; transition: all 0.25s ease;
  white-space: nowrap; font-family: inherit;
}
.filter-chip:hover { border-color: var(--primary); color: var(--primary); background: var(--primary-alpha); }
.filter-chip.active {
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  border-color: var(--primary); color: white;
}
</style>
