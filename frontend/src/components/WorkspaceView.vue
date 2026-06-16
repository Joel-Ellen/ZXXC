<template>
  <div class="flex h-screen">
    <!-- 左侧边栏 -->
    <aside class="w-72 bg-gray-900 border-r border-gray-800 flex flex-col flex-shrink-0">
      <!-- 用户信息 -->
      <div class="px-5 py-4 border-b border-gray-800 flex items-center justify-between">
        <div>
          <p class="text-sm font-semibold text-white">{{ user?.display_name || user?.user_id }}</p>
          <p class="text-xs text-gray-500">{{ user?.role === 'ADMIN' ? '管理员' : '学生' }}</p>
        </div>
        <button @click="$emit('logout')" class="text-xs text-gray-500 hover:text-red-400 transition" title="退出登录">退出</button>
      </div>

      <!-- 进度条 -->
      <div class="px-5 py-3 border-b border-gray-800">
        <div class="flex justify-between text-xs text-gray-500 mb-1.5">
          <span>学习进度</span>
          <span>{{ mastered }}/{{ totalPath }} · {{ progress }}%</span>
        </div>
        <div class="h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div class="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-500" :style="{ width: progress + '%' }"></div>
        </div>
      </div>

      <!-- 学习路径 -->
      <div class="flex-1 overflow-y-auto px-3 py-3">
        <p class="text-xs font-medium text-gray-500 uppercase tracking-wider px-2 mb-2">学习路径</p>
        <div v-if="pathNodes.length === 0" class="text-xs text-gray-600 px-2">暂无学习路径，请先完成冷启动</div>
        <div v-for="node in pathNodes" :key="node.id" class="mb-1">
          <button
            @click="$emit('selectNode', node.id)"
            :class="[
              'w-full text-left px-3 py-2.5 rounded-lg text-sm transition flex items-center gap-3',
              node.id === currentNode
                ? 'bg-indigo-600/20 border border-indigo-500/30 text-white'
                : 'hover:bg-gray-800 text-gray-400 border border-transparent'
            ]"
          >
            <span :class="[
              'w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0',
              (node.mastery ?? 0) >= 0.85 ? 'bg-green-500/20 text-green-400' :
              (node.mastery ?? 0) >= 0.65 ? 'bg-yellow-500/20 text-yellow-400' :
              'bg-gray-700 text-gray-400'
            ]">{{ node.order }}</span>
            <span class="truncate">{{ node.title }}</span>
            <span v-if="(node.mastery ?? 0) >= 0.85" class="text-[10px] text-green-400 flex-shrink-0">已掌握</span>
          </button>
        </div>
      </div>

      <!-- 智能体状态 -->
      <div class="px-4 py-3 border-t border-gray-800">
        <p class="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">智能体状态</p>
        <div v-for="s in statuses" :key="s.key" class="flex items-center gap-2 text-xs text-gray-400 py-1">
          <span :class="s.active ? 'bg-green-500' : 'bg-gray-600'" class="w-1.5 h-1.5 rounded-full flex-shrink-0"></span>
          <span class="w-16 flex-shrink-0">{{ s.label }}</span>
          <span class="text-gray-600 truncate">{{ s.phase }}</span>
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- 顶部导航 -->
      <header class="h-12 bg-gray-900 border-b border-gray-800 flex items-center px-5 gap-3 flex-shrink-0">
        <span class="text-xs text-gray-500">当前节点</span>
        <span class="text-sm text-white font-medium">{{ nodeTitle || '请从左侧选择知识点' }}</span>
        <span v-if="loadingNode" class="text-xs text-indigo-400">加载中...</span>
        <div class="flex-1"></div>
        <span v-if="radar" class="text-xs text-gray-500">
          综合能力: {{ (radar.reduce((a,b)=>a+b,0)/5).toFixed(2) }}
        </span>
      </header>

      <!-- 内容区 (三栏) -->
      <div class="flex-1 flex overflow-hidden">
        <!-- 中栏：资源卡片 -->
        <div class="flex-1 overflow-y-auto p-5 space-y-4 bg-gray-950">
          <div v-if="cards.length === 0" class="text-center text-gray-600 mt-20">
            <p class="text-4xl mb-4">📚</p>
            <p>选择一个知识点开始学习</p>
            <p class="text-xs mt-2">系统将自动生成概念导图、代码示例、互动练习、视频摘要和诊断测验</p>
          </div>
          <div v-for="card in cards" :key="card.resource_id" class="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div class="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-xs font-medium px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400">{{ cardLabel(card.card_type) }}</span>
                <span class="text-[10px] text-gray-600">{{ agentLabel(card.card_type) }}</span>
              </div>
              <span class="text-[10px] text-gray-600">难度 {{ (card.difficulty * 100).toFixed(0) }}%</span>
            </div>
            <div class="p-5">
              <MarkdownContent :content="card.content" />
            </div>
          </div>
        </div>

        <!-- 右栏：辅导对话 + 评估报告 -->
        <div class="w-96 border-l border-gray-800 flex flex-col flex-shrink-0 bg-gray-900/50">
          <!-- 辅导对话 -->
          <div class="flex-1 flex flex-col min-h-0">
            <div class="px-4 py-3 border-b border-gray-800 text-xs font-medium text-gray-400">智能辅导</div>
            <div class="flex-1 overflow-y-auto px-4 py-3 space-y-3" ref="chatContainer">
              <div v-for="msg in messages" :key="msg.id" :class="msg.role === 'user' ? 'flex justify-end' : 'flex gap-2'">
                <div v-if="msg.role === 'assistant'" class="w-6 h-6 rounded-full bg-indigo-600 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">AI</div>
                <div :class="[
                  'max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm',
                  msg.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-200'
                ]">
                  <MarkdownContent v-if="msg.content" :content="msg.content" />
                  <span v-else-if="msg.streaming" class="text-gray-500">生成中...</span>
                  <div v-if="msg.mermaid" class="mt-2 p-2 bg-gray-900 rounded-lg border border-gray-700 text-xs overflow-x-auto">
                    <pre class="text-gray-300">{{ msg.mermaid }}</pre>
                  </div>
                </div>
              </div>
            </div>
            <!-- 输入框 -->
            <div class="px-3 py-3 border-t border-gray-800">
              <form @submit.prevent="sendMsg" class="flex gap-2">
                <input
                  v-model="tutorInput"
                  type="text"
                  placeholder="向辅导智能体提问..."
                  class="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500 transition"
                />
                <button type="submit" :disabled="!tutorInput.trim()" class="px-3 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-500 disabled:opacity-50 transition">发送</button>
              </form>
            </div>
          </div>

          <!-- 评估报告 -->
          <div v-if="report" class="border-t border-gray-800 max-h-64 overflow-y-auto">
            <div class="px-4 py-2 border-b border-gray-800 text-xs font-medium text-gray-400">能力评估报告</div>
            <div class="px-4 py-3 text-xs text-gray-400 space-y-2">
              <div v-for="(val, idx) in radar" :key="idx" class="flex items-center gap-2">
                <span class="w-20 flex-shrink-0">{{ ['概念理解','代码工程','逻辑推理','错题抗挫','时间管理'][idx] }}</span>
                <div class="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                  <div class="h-full rounded-full" :class="val >= 0.7 ? 'bg-green-500' : val >= 0.5 ? 'bg-yellow-500' : 'bg-red-500'" :style="{ width: (val*100) + '%' }"></div>
                </div>
                <span class="w-10 text-right">{{ (val*100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from "vue";
import MarkdownContent from "./MarkdownContent.vue";

const props = defineProps({
  user: Object,
  currentNode: String,
  nodeTitle: String,
  cards: Array,
  pathNodes: Array,
  messages: Array,
  radar: Array,
  report: String,
  progress: Number,
  mastered: Number,
  totalPath: Number,
  statuses: Array,
  busy: Boolean,
  loadingNode: Boolean,
  cardLabel: Function,
  agentLabel: Function,
  parseQuiz: Function,
});

const emit = defineEmits(["selectNode", "submitQuiz", "sendTutor", "logout"]);

const tutorInput = ref("");
const chatContainer = ref(null);

function sendMsg() {
  if (!tutorInput.value.trim()) return;
  emit("sendTutor", tutorInput.value);
  tutorInput.value = "";
}

watch(() => props.messages.length, () => {
  nextTick(() => {
    if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
  });
});
</script>
