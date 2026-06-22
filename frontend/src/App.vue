<template>
  <div class="min-h-screen text-text-primary font-sans relative">
    <AuroraBackground :reduce-motion="false" />

    <LandingView
      v-if="showLanding"
      @enter="onEnterApp"
    />

    <template v-else>
      <div
        v-if="bootMode === 'loading'"
        class="relative z-10 flex h-screen items-center justify-center animate-fadeIn"
      >
        <div class="text-center animate-fadeIn">
          <div class="relative mx-auto mb-6 h-20 w-20">
            <div class="absolute inset-0 rounded-full border-2 border-primary/15 animate-spin-slow" />
            <div class="absolute inset-1 rounded-full border-2 border-t-secondary border-r-transparent border-b-transparent border-l-transparent animate-spin" style="animation-duration: 1.1s;" />
            <div class="absolute inset-2 rounded-full border-2 border-b-tertiary border-t-transparent border-r-transparent border-l-transparent animate-spin" style="animation-duration: 1.6s; animation-direction: reverse;" />
            <div class="absolute inset-0 flex items-center justify-center">
              <span class="text-xl font-black gradient-text">EA</span>
            </div>
          </div>
          <p class="text-sm font-medium tracking-wide text-text-secondary">正在初始化学习工作台...</p>
          <p class="mt-2 text-xs text-text-muted">多智能体协作编排中</p>
        </div>
      </div>

      <AuthView
        v-else-if="bootMode === 'login'"
        @login="onLogin"
        @register="onRegister"
        @go-home="goHome"
      />

      <CourseSelectionView
        v-else-if="bootMode === 'course_selection'"
        :courses="availableCourses"
        :enrolled="enrolledCourses"
        :loading="isBusy"
        @select="onCourseSelect"
        @go-home="goHome"
      />

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
        :last-diagnostic="workspaceLastDiagnostic"
        :get-card-label="getCardLabel"
        :get-agent-label="getAgentLabel"
        :parse-quiz="parseQuiz"
        :active-course="workspaceActiveCourse"
        :enrolled-courses="workspaceEnrolledCourses"
        @select-node="loadNode"
        @submit-quiz="submitQuiz"
        @send-tutor="onSendTutorMessage"
        @submit-probe="submitProbe"
        @logout="handleLogout"
        @go-home="goHome"
        @switch-course="onSwitchCourse"
      />
    </template>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, onMounted, ref } from "vue";
import AuroraBackground from "./components/AuroraBackground.vue";
import { useEduAgent } from "./composables/useEduAgent";
import { useTheme } from "./composables/useTheme.js";

const LandingView = defineAsyncComponent(() => import("./components/LandingView.vue"));
const AuthView = defineAsyncComponent(() => import("./components/AuthView.vue"));
const CourseSelectionView = defineAsyncComponent(() => import("./components/CourseSelectionView.vue"));
const PremiumWorkspace = defineAsyncComponent(() => import("./components/PremiumWorkspace.vue"));

useTheme();

const initialPreviewWorkspace = detectPreviewWorkspace();
const showLanding = ref(!initialPreviewWorkspace);
const workspacePreview = ref(initialPreviewWorkspace);

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
    content: `## 学习目标
栈与队列都是受限线性表，重点不是会写 API，而是理解它们对顺序约束的差异。

- 栈：后进先出，适合处理最近未闭合的问题。
- 队列：先进先出，适合按到达顺序处理任务。
- 当你需要解释“为什么这样设计”时，优先回到约束本身。`,
    metadata: {
      render_type: "concept_map",
      title: "栈与队列",
      summary: "栈和队列都在管理顺序约束，关键是理解 LIFO 与 FIFO 分别适合什么问题。",
      bullets: [
        "栈：后进先出，适合处理最近未闭合的问题。",
        "队列：先进先出，适合按到达顺序处理任务。",
        "先理解约束，再理解具体 API。",
      ],
      mermaid_source: `graph TD
ROOT["栈与队列"]
ROOT --> STACK["栈：LIFO"]
ROOT --> QUEUE["队列：FIFO"]
STACK --> STACK_USE["括号匹配 / 回溯"]
QUEUE --> QUEUE_USE["调度 / 广度优先遍历"]`,
    },
  },
  {
    resource_id: "preview-code",
    card_type: "code_snippet",
    content: `\`\`\`js
class Queue {
  constructor() {
    this.items = [];
    this.head = 0;
  }

  enqueue(value) {
    this.items.push(value);
  }

  dequeue() {
    return this.head < this.items.length ? this.items[this.head++] : undefined;
  }
}
\`\`\``,
    metadata: {
      render_type: "code_snippet",
      title: "队列实现示例",
      language: "js",
      code: `class Queue {
  constructor() {
    this.items = [];
    this.head = 0;
  }

  enqueue(value) {
    this.items.push(value);
  }

  dequeue() {
    return this.head < this.items.length ? this.items[this.head++] : undefined;
  }
}`,
      explanation: "这个实现用 `head` 指针避免了每次 `shift()` 带来的整体搬移，更适合讲清楚队列的先进先出约束。",
    },
  },
  {
    resource_id: "preview-exercise",
    card_type: "interactive_exercise",
    content: `## 互动练习
给定一个只包含 \`(\`、\`)\`、\`[\`、\`]\` 的字符串，判断括号是否有效。

先写出栈状态如何变化，再补完整体代码。`,
    metadata: {
      render_type: "interactive_exercise",
      title: "括号匹配练习",
      prompt: "先用栈状态变化解释你的思路，再落到代码实现。",
      steps: [
        "为每个左括号执行入栈。",
        "遇到右括号时检查栈顶是否为匹配的左括号。",
        "遍历结束后确认栈是否为空。",
      ],
      checkpoints: [
        "能解释为什么要匹配最近一个未闭合括号。",
        "能处理空字符串和单个右括号这类边界情况。",
        "代码里没有遗漏栈空检查。",
      ],
    },
  },
  {
    resource_id: "preview-video",
    card_type: "video_summary",
    content: `## 视频摘要
如果你已经知道栈和队列的 API，还总是分不清它们的题型差异，就先回到“顺序约束”这条主线：
- 栈适合处理最近发生、尚未闭合的状态。
- 队列适合处理按到达顺序推进的任务。
- 真题里先判断约束，再选数据结构。`,
    metadata: {
      render_type: "video_summary",
      title: "栈与队列速览",
      summary: "这段内容强调“先看顺序约束，再选数据结构”，帮你把常见题型和栈/队列的适配关系对齐。",
      key_points: [
        "栈关注最近状态，队列关注到达顺序。",
        "选型时先看约束，不要先背 API。",
        "括号匹配、回溯更常见于栈；调度、BFS 更常见于队列。",
      ],
      duration_minutes: 6,
      video_url: "https://www.bilibili.com",
    },
  },
  {
    resource_id: "preview-quiz",
    card_type: "diagnostic_quiz",
    content: "栈的核心约束是后进先出，适合处理最近未闭合的问题。队列的核心约束是先进先出，适合按到达顺序处理任务。",
    metadata: {
      render_type: "diagnostic_quiz",
      title: "节点诊断",
      questions: [
        {
          id: "q1",
          prompt: "为什么括号匹配通常更适合用栈？",
          options: [
            "因为它总是要匹配最近一个未闭合的左括号",
            "因为栈支持随机访问",
            "因为队列不能存字符",
            "因为栈的时间复杂度总是更低",
          ],
          answer_index: 0,
          explanation: "括号匹配要优先处理最近未闭合状态，这正好符合 LIFO。",
        },
        {
          id: "q2",
          prompt: "下面哪种场景更符合队列？",
          options: [
            "函数调用栈回退",
            "浏览器撤销操作",
            "按到达顺序处理任务调度",
            "表达式括号检查",
          ],
          answer_index: 2,
          explanation: "任务调度强调先到先处理，更符合 FIFO。",
        },
      ],
      pass_threshold: 0.65,
    },
  },
];

const previewMessages = ref([
  {
    id: "preview-a1",
    role: "assistant",
    content: "你现在位于“栈与队列”节点。建议先完成概念目标，再看代码示例，最后提交诊断测验。",
  },
  {
    id: "preview-u1",
    role: "user",
    content: "为什么括号匹配适合用栈？",
  },
  {
    id: "preview-a2",
    role: "assistant",
    content: "因为每个右括号都需要匹配最近出现且尚未闭合的左括号，这正好符合后进先出的约束。",
  },
]);

const previewStatuses = [
  { key: "doc", kind: "doc", label: "文档智能体", phase: "资源就绪", progress: 100, active: true },
  { key: "quiz", kind: "quiz", label: "评估智能体", phase: "测验可用", progress: 50, active: true },
  { key: "path", kind: "path", label: "路径规划", phase: "5 个节点", progress: 100, active: true },
];

const {
  bootMode,
  isSubmittingProbe,
  isBusy,
  isLoadingNode,
  currentNode,
  currentUser,
  capabilityRadar,
  currentCards,
  currentNodeTitle,
  currentPathNodes,
  messages,
  infoMessage,
  agentStatuses,
  probe,
  probeCollected,
  probeTotal,
  lastDiagnostic,
  overallProgress,
  masteredCount,
  activeCourse,
  availableCourses,
  enrolledCourses,
  handleLogin,
  handleRegister,
  handleLogout,
  bootstrap,
  submitProbe,
  loadNode,
  submitQuiz,
  sendTutorMessage,
  getCardLabel,
  getAgentLabel,
  parseQuiz,
  handleEnrollCourse,
  handleSwitchCourse,
} = useEduAgent();

const workspaceUser = computed(() =>
  workspacePreview.value ? { user_id: "preview_user", display_name: "学习者" } : currentUser.value,
);
const workspaceCurrentNode = computed(() => (workspacePreview.value ? "stack-queue" : currentNode.value));
const workspaceCards = computed(() => (workspacePreview.value ? previewCards : currentCards.value));
const workspacePathNodes = computed(() => (workspacePreview.value ? previewPathNodes : currentPathNodes.value));
const workspaceNodeTitle = computed(() => (workspacePreview.value ? "栈与队列" : currentNodeTitle.value));
const workspaceMessages = computed(() => (workspacePreview.value ? previewMessages.value : messages.value));
const workspaceCapabilityRadar = computed(() => (workspacePreview.value ? [0.78, 0.64, 0.71, 0.52, 0.68] : capabilityRadar.value));
const workspaceOverallProgress = computed(() => (workspacePreview.value ? 40 : overallProgress.value));
const workspaceMasteredCount = computed(() => (workspacePreview.value ? 2 : masteredCount.value));
const workspaceLastDiagnostic = computed(() => (workspacePreview.value ? null : lastDiagnostic.value));
const workspaceStatuses = computed(() => (workspacePreview.value ? previewStatuses : agentStatuses.value));
const workspaceInfoMessage = computed(() => (
  workspacePreview.value
    ? "当前为工作台预览模式，交互数据不会写入学习进度。"
    : infoMessage.value
));
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

async function onSendTutorMessage(query) {
  if (workspacePreview.value) {
    await sendPreviewTutorMessage(query);
    return;
  }

  await sendTutorMessage(query);
}

function onSwitchCourse(courseId) {
  handleSwitchCourse(courseId);
}

onMounted(() => {
  if (workspacePreview.value) {
    workspacePreview.value = true;
    showLanding.value = false;
    bootMode.value = "ready";
    return;
  }

  if (window.location.hash === "#app") {
    showLanding.value = false;
    bootstrap();
  }
});

function detectPreviewWorkspace() {
  if (typeof window === "undefined") {
    return false;
  }

  const params = new URLSearchParams(window.location.search);
  return params.get("previewWorkspace") === "1";
}

async function sendPreviewTutorMessage(query) {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) {
    return;
  }

  const timestamp = Date.now();
  const userMsg = {
    id: `preview-u-${timestamp}`,
    role: "user",
    content: normalizedQuery,
  };
  const assistantMsg = {
    id: `preview-a-${timestamp}`,
    role: "assistant",
    content: "",
    mermaidSource: "",
    isStreaming: true,
  };

  previewMessages.value = [...previewMessages.value, userMsg, assistantMsg];
  await new Promise((resolve) => window.setTimeout(resolve, 420));
  previewMessages.value = previewMessages.value.map((message) => (
    message.id === assistantMsg.id
      ? {
          ...message,
          content: buildPreviewTutorReply(normalizedQuery),
          isStreaming: false,
        }
      : message
  ));
}

function buildPreviewTutorReply(query) {
  if (/[括号栈]/.test(query)) {
    return "可以先把问题还原成顺序约束：每个右括号都要匹配最近一个尚未闭合的左括号，所以先检查最近入栈的元素是否正确，这正是后进先出的典型场景。";
  }

  if (/队列|调度|任务/.test(query)) {
    return "如果题目强调按到达顺序处理任务、请求或事件，优先考虑队列。判断关键不在名字，而在系统是否要求先到先处理。";
  }

  if (/区别|比较|对比/.test(query)) {
    return "比较栈和队列时，最稳的表达方式是先说顺序约束，再说典型场景：栈处理最近未完成状态，队列处理按到达顺序排队的任务。";
  }

  return "预览模式下，这里会用本地演示回答来模拟辅导链路。围绕“顺序约束、典型场景、为什么这样设计”三个角度提问，会最接近真实学习过程。";
}
</script>
