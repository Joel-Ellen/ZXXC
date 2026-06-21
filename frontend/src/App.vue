<template>
  <div class="min-h-screen text-text-primary font-sans relative">
    <!-- Dynamic aurora background -->
    <AuroraBackground :reduce-motion="false" />

    <!-- Landing page -->
    <LandingView
      v-if="showLanding"
      @enter="onEnterApp"
    />

    <!-- App states -->
    <template v-else>
      <!-- 加载中 -->
      <div
        v-if="bootMode === 'loading'"
        class="relative z-10 flex items-center justify-center h-screen animate-fadeIn"
      >
        <div class="text-center animate-fadeIn">
          <div class="relative w-20 h-20 mx-auto mb-6">
            <div class="absolute inset-0 rounded-full border-2 border-primary/15 animate-spin-slow" />
            <div class="absolute inset-1 rounded-full border-2 border-t-secondary border-r-transparent border-b-transparent border-l-transparent animate-spin" style="animation-duration: 1.1s;" />
            <div class="absolute inset-2 rounded-full border-2 border-b-tertiary border-t-transparent border-r-transparent border-l-transparent animate-spin" style="animation-duration: 1.6s; animation-direction: reverse;" />
            <div class="absolute inset-0 flex items-center justify-center">
              <span class="text-xl font-black gradient-text">EA</span>
            </div>
          </div>
          <p class="text-sm font-medium text-text-secondary tracking-wide">正在初始化学习工作台...</p>
          <p class="mt-2 text-xs text-text-muted">多智能体协作编排中</p>
        </div>
      </div>

      <!-- 登录 / 注册 -->
      <AuthView
        v-else-if="bootMode === 'login'"
        @login="onLogin"
        @register="onRegister"
        @go-home="goHome"
      />

      <!-- 课程选择 -->
      <CourseSelectionView
        v-else-if="bootMode === 'course_selection'"
        :courses="availableCourses"
        :enrolled="enrolledCourses"
        :loading="isBusy"
        @select="onCourseSelect"
        @go-home="goHome"
      />

      <!-- 主工作台 (探针 + 就绪) -->
      <PremiumWorkspace
        v-else-if="bootMode === 'probe' || bootMode === 'ready'"
        :boot-mode="bootMode"
        :user="workspaceUser"
        :current-node="workspaceCurrentNode"
        :cards="workspaceCards"
        :path-nodes="workspacePathNodes"
        :node-title="workspaceNodeTitle"
        :messages="workspaceMessages"
        :capability-radar="workspaceCapabilityRadar"
        :overall-progress="workspaceOverallProgress"
        :mastered-count="workspaceMasteredCount"
        :statuses="workspaceStatuses"
        :info-message="workspaceInfoMessage"
        :is-busy="isBusy"
        :is-loading-node="isLoadingNode"
        :is-submitting-probe="isSubmittingProbe"
        :probe="probe"
        :probe-collected="probeCollected"
        :probe-total="probeTotal"
        :get-card-label="getCardLabel"
        :get-agent-label="getAgentLabel"
        :parse-quiz="parseQuiz"
        :active-course="workspaceActiveCourse"
        :enrolled-courses="workspaceEnrolledCourses"
        @select-node="loadNode"
        @submit-quiz="submitQuiz"
        @send-tutor="sendTutorMessage"
        @submit-probe="submitProbe"
        @logout="handleLogout"
        @go-home="goHome"
        @switch-course="onSwitchCourse"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import AuroraBackground from "./components/AuroraBackground.vue";
import AuthView from "./components/AuthView.vue";
import CourseSelectionView from "./components/CourseSelectionView.vue";
import LandingView from "./components/LandingView.vue";
import PremiumWorkspace from "./components/PremiumWorkspace.vue";
import { useEduAgent } from "./composables/useEduAgent";
import { useTheme } from "./composables/useTheme.js";

// Initialize theme system
useTheme();

const showLanding = ref(true);
const workspacePreview = ref(false);

const previewCourse = {
  course_id: "data_structures",
  title_cn: "数据结构与算法",
  icon: "📚",
  progress: 0.42,
};

const previewPathNodes = [
  { id: "array", order: 1, title: "数组与顺序表", mastery: 0.92 },
  { id: "linked-list", order: 2, title: "链表结构", mastery: 0.74 },
  { id: "stack-queue", order: 3, title: "栈与队列", mastery: 0.46 },
  { id: "tree", order: 4, title: "树与递归", mastery: 0.18 },
  { id: "graph", order: 5, title: "图与搜索", mastery: 0.08 },
];

const previewCards = [
  {
    resource_id: "preview-concept",
    card_type: "concept_map",
    content: "## 学习目标\n栈与队列是受限线性表，重点掌握操作约束、复杂度边界以及典型应用场景。\n\n- 栈：后进先出，适合递归模拟、括号匹配、单调结构。\n- 队列：先进先出，适合层序遍历、缓冲调度、广度优先搜索。",
  },
  {
    resource_id: "preview-code",
    card_type: "code_snippet",
    content: "```js\nclass Queue {\n  constructor() {\n    this.items = [];\n    this.head = 0;\n  }\n\n  enqueue(value) {\n    this.items.push(value);\n  }\n\n  dequeue() {\n    return this.head < this.items.length ? this.items[this.head++] : undefined;\n  }\n}\n```",
  },
  {
    resource_id: "preview-exercise",
    card_type: "interactive_exercise",
    content: "## 互动练习\n给定一个只包含 `(`、`)`、`[`、`]` 的字符串，判断括号是否有效。先写出栈状态变化，再提交代码。",
  },
  {
    resource_id: "preview-quiz",
    card_type: "diagnostic_quiz",
    content: "栈的核心约束是后进先出，适合处理最近未闭合的问题。队列的核心约束是先进先出，适合按到达顺序处理任务。",
  },
];

const previewMessages = [
  {
    id: "preview-a1",
    role: "assistant",
    content: "你现在处在“栈与队列”节点。建议先完成概念目标，再看代码示例，最后提交诊断测验。",
  },
  {
    id: "preview-u1",
    role: "user",
    content: "为什么括号匹配适合用栈？",
  },
  {
    id: "preview-a2",
    role: "assistant",
    content: "因为每个右括号都需要匹配最近出现且尚未闭合的左括号，这正好符合后进先出的结构约束。",
  },
];

const previewStatuses = [
  { key: "doc", kind: "doc", label: "文档智能体", phase: "资源就绪", progress: 100, active: true },
  { key: "quiz", kind: "quiz", label: "评估智能体", phase: "测验可用", progress: 50, active: true },
  { key: "path", kind: "path", label: "路径规划", phase: "5 个节点", progress: 100, active: true },
];

const {
  bootMode, isSubmittingProbe, isBusy, isLoadingNode,
  currentNode, currentUser, capabilityRadar, diagnosticReport,
  currentCards, currentNodeTitle, currentPathNodes,
  messages, infoMessage, agentStatuses, probe, probeCollected, probeTotal,
  overallProgress, masteredCount,
  activeCourse, availableCourses, enrolledCourses,
  handleLogin, handleRegister, handleLogout,
  bootstrap, submitProbe, loadNode, submitQuiz, sendTutorMessage,
  getCardLabel, getAgentLabel, parseQuiz,
  handleEnrollCourse, handleSwitchCourse,
} = useEduAgent();

const workspaceUser = computed(() =>
  workspacePreview.value ? { user_id: "preview_user", display_name: "学习者" } : currentUser.value,
);
const workspaceCurrentNode = computed(() => (workspacePreview.value ? "stack-queue" : currentNode.value));
const workspaceCards = computed(() => (workspacePreview.value ? previewCards : currentCards.value));
const workspacePathNodes = computed(() => (workspacePreview.value ? previewPathNodes : currentPathNodes.value));
const workspaceNodeTitle = computed(() => (workspacePreview.value ? "栈与队列" : currentNodeTitle.value));
const workspaceMessages = computed(() => (workspacePreview.value ? previewMessages : messages.value));
const workspaceCapabilityRadar = computed(() => (workspacePreview.value ? [0.78, 0.64, 0.71, 0.52, 0.68] : capabilityRadar.value));
const workspaceOverallProgress = computed(() => (workspacePreview.value ? 40 : overallProgress.value));
const workspaceMasteredCount = computed(() => (workspacePreview.value ? 2 : masteredCount.value));
const workspaceStatuses = computed(() => (workspacePreview.value ? previewStatuses : agentStatuses.value));
const workspaceInfoMessage = computed(() => (workspacePreview.value ? "当前为工作台预览模式，交互数据不会写入学习进度。" : infoMessage.value));
const workspaceActiveCourse = computed(() => (workspacePreview.value ? previewCourse : activeCourse.value));
const workspaceEnrolledCourses = computed(() => (workspacePreview.value ? [previewCourse] : enrolledCourses.value));

async function onLogin(userId, password, captchaToken, captchaAnswer) {
  await handleLogin(userId, password, captchaToken, captchaAnswer);
  await bootstrap();
}

async function onRegister(userId, email, password, captchaToken, captchaAnswer) {
  await handleRegister(userId, email, password, captchaToken, captchaAnswer);
  await bootstrap();
}

function onEnterApp() {
  showLanding.value = false;
  workspacePreview.value = false;
  bootstrap();
}

function goHome() {
  showLanding.value = true;
}

function onCourseSelect(courseId) {
  handleEnrollCourse(courseId);
}

function onSwitchCourse(courseId) {
  handleSwitchCourse(courseId);
}

onMounted(() => {
  const params = new URLSearchParams(window.location.search);
  if (params.get("previewWorkspace") === "1") {
    workspacePreview.value = true;
    showLanding.value = false;
    bootMode.value = "ready";
    return;
  }

  // Check URL hash for direct app access
  if (window.location.hash === "#app") {
    showLanding.value = false;
    bootstrap();
  }
});
</script>
