<template>
  <div
    class="workspace-shell relative z-10 flex h-screen overflow-hidden font-sans text-text-primary animate-fadeIn"
    :class="{
      'is-high-contrast': highContrast,
      'is-reduced-motion': reduceMotion,
    }"
    :style="{ fontSize: `${fontSize}px` }"
  >
    <SidebarRail
      :active-panel="sidebarPanel"
      :drawer-open="drawerOpen"
      :path-count="pathNodes.length"
      @select="onSidebarSelect"
    />

    <div class="relative flex min-w-0 flex-1 flex-col">
      <header class="glass-panel relative z-20 px-4 py-3 sm:px-5 lg:px-6">
        <div class="flex flex-wrap items-center gap-3 lg:flex-nowrap">
          <div class="flex flex-shrink-0 items-center gap-3">
            <div class="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-primary to-secondary text-sm font-black text-primary-text shadow-glow">
              EA
            </div>
            <div class="hidden sm:block">
              <span class="block text-sm font-black leading-tight tracking-tight text-text-primary">
                EduAgent
              </span>
              <span class="block text-[10px] font-medium tracking-[0.12em] text-text-muted">
                课程学习工作台
              </span>
            </div>
          </div>

          <nav class="hidden flex-shrink-0 items-center gap-1 rounded-full border border-subtle bg-card p-1 xl:flex">
            <button
              v-for="item in workspaceNav"
              :key="item.key"
              type="button"
              class="focus-ring rounded-full px-3 py-1.5 text-[11px] font-semibold tracking-[0.08em] transition-all duration-200"
              :class="navButtonClass(item.key)"
              @click="handleNav(item.key)"
            >
              {{ item.label }}
            </button>
          </nav>

          <div class="order-3 hidden min-w-[320px] flex-1 justify-start overflow-hidden md:flex xl:order-none xl:justify-center">
            <TopStatusBar :statuses="statuses" />
          </div>

          <div class="ml-auto flex flex-shrink-0 items-center gap-2 sm:gap-3">
            <div v-if="activeCourse || enrolledCourses.length" class="relative">
              <button
                type="button"
                class="focus-ring flex items-center gap-2 rounded-full border border-subtle bg-card px-3.5 py-1.5 text-[11px] font-semibold text-text-secondary transition-all duration-200 hover:border-primary/30 hover:bg-card-hover hover:text-primary"
                @click="courseMenuOpen = !courseMenuOpen"
              >
                <span class="text-base leading-none">{{ activeCourse?.icon || "📘" }}</span>
                <span class="hidden max-w-[96px] truncate sm:inline xl:max-w-[120px]">{{ activeCourse?.title_cn || "课程" }}</span>
                <svg
                  width="10"
                  height="10"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="3"
                  class="transition-transform duration-200"
                  :class="courseMenuOpen ? 'rotate-180' : ''"
                >
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </button>

              <transition name="fade">
                <div
                  v-if="courseMenuOpen"
                  class="absolute right-0 top-full z-50 mt-2 w-64 rounded-2xl border border-subtle bg-space-panel p-2 shadow-2xl backdrop-blur-xl"
                  @click.stop
                >
                  <p class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.14em] text-text-muted">已选课程</p>
                  <button
                    v-for="course in enrolledCourses"
                    :key="course.course_id"
                    type="button"
                    class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-colors duration-150 hover:bg-card"
                    :class="course.course_id === activeCourse?.course_id ? 'bg-primary-soft/20 text-primary' : 'text-text-secondary'"
                    @click="onSwitchCourse(course.course_id)"
                  >
                    <span class="text-lg">{{ course.icon || "📘" }}</span>
                    <div class="min-w-0 flex-1">
                      <span class="block truncate text-sm font-medium">{{ course.title_cn }}</span>
                      <span class="block text-[10px] text-text-muted">{{ course.progress ? Math.round(course.progress * 100) : 0 }}%</span>
                    </div>
                    <IconCheck
                      v-if="course.course_id === activeCourse?.course_id"
                      :size="14"
                      class="shrink-0 text-primary"
                    />
                  </button>
                  <div class="my-1 h-px bg-[var(--border-subtle)]" />
                  <button
                    type="button"
                    class="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-sm text-text-muted transition-colors hover:bg-card hover:text-primary"
                    @click="$emit('go-home')"
                  >
                    <span class="text-base">+</span>
                    浏览更多课程
                  </button>
                </div>
              </transition>
              <div v-if="courseMenuOpen" class="fixed inset-0 z-40" @click="courseMenuOpen = false" />
            </div>

            <button
              type="button"
              class="focus-ring rounded-full border border-subtle bg-card px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted transition-all duration-200 hover:border-primary/30 hover:bg-primary-soft hover:text-primary"
              @click="$emit('go-home')"
            >
              首页
            </button>

            <span class="hidden text-xs font-medium text-text-secondary sm:inline">
              {{ user?.display_name || user?.user_id || "未登录" }}
            </span>

            <button
              type="button"
              class="focus-ring rounded-full border border-subtle bg-card px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted transition-all duration-200 hover:border-error/30 hover:bg-error-soft hover:text-error"
              @click="$emit('logout')"
            >
              退出
            </button>
          </div>
        </div>

        <div class="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-[var(--border-strong)] to-transparent" />
      </header>

      <div class="relative flex min-h-0 flex-1 flex-col bg-space-bg/35">
        <section class="border-b border-subtle px-4 py-4 backdrop-blur-sm sm:px-5 lg:px-6">
          <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-start">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">学习驾驶舱</p>
                <span class="rounded-full border border-primary/20 bg-primary-soft px-3 py-1 text-[11px] font-semibold text-primary">
                  {{ studyStage }}
                </span>
              </div>

              <div class="mt-3 flex flex-wrap items-end gap-x-4 gap-y-2">
                <h1 class="truncate text-[30px] font-black tracking-tight text-text-primary lg:text-[34px]">
                  {{ activeCourse?.title_cn || "课程工作台" }}
                </h1>
                <span class="rounded-full border border-subtle bg-card px-3 py-1 text-[11px] font-semibold text-text-secondary">
                  {{ currentNodeCaption }}
                </span>
              </div>

              <p class="mt-3 max-w-3xl text-sm leading-6 text-text-muted">
                当前节点：
                <span class="font-semibold text-text-secondary">{{ nodeTitle || "等待生成学习路径" }}</span>
                <span v-if="nextNode" class="ml-1">· 下一建议节点：{{ nextNode.title }}</span>
              </p>

              <div class="mt-4 grid gap-3 lg:grid-cols-2">
                <div class="rounded-[22px] border border-subtle bg-card p-4 shadow-card">
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">当前建议</p>
                  <p class="mt-2 text-base font-semibold text-text-primary">{{ focusTitle }}</p>
                  <p class="mt-2 text-sm leading-6 text-text-muted">{{ focusDetail }}</p>
                </div>
                <div class="rounded-[22px] border border-subtle bg-card p-4 shadow-card">
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">学习秩序</p>
                  <p class="mt-2 text-base font-semibold text-text-primary">{{ learningSequenceTitle }}</p>
                  <p class="mt-2 text-sm leading-6 text-text-muted">{{ learningSequenceDetail }}</p>
                </div>
              </div>

              <div
                v-if="infoMessage"
                class="mt-4 rounded-[18px] border border-primary/20 bg-primary-soft/80 px-4 py-3 text-sm text-primary shadow-card"
              >
                {{ infoMessage }}
              </div>
            </div>

            <div class="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:min-w-[520px] xl:grid-cols-4">
              <div
                v-for="metric in metrics"
                :key="metric.label"
                class="rounded-[18px] border border-subtle bg-card px-4 py-3 shadow-card"
              >
                <p class="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">{{ metric.label }}</p>
                <p class="mt-2 text-xl font-black text-text-primary">{{ metric.value }}</p>
                <p class="mt-1 text-[11px] leading-5 text-text-muted">{{ metric.detail }}</p>
              </div>
            </div>
          </div>

          <div class="mt-4 grid gap-2 md:hidden">
            <div
              v-for="status in compactStatuses"
              :key="status.key"
              class="rounded-[18px] border bg-card px-4 py-3 shadow-card"
              :class="status.panelClass"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0">
                  <p class="text-[10px] font-black uppercase tracking-[0.12em] text-text-muted">{{ status.label }}</p>
                  <p class="mt-1 text-sm font-semibold text-text-primary">{{ status.phase }}</p>
                </div>
                <span class="text-xs font-mono text-text-muted">{{ status.progress }}%</span>
              </div>
            </div>
          </div>
        </section>

        <section class="border-b border-subtle px-4 py-3 xl:hidden sm:px-5">
          <div class="flex gap-2 overflow-x-auto pb-1">
            <button
              v-for="item in mobileActions"
              :key="item.key"
              type="button"
              class="focus-ring shrink-0 rounded-full border px-3.5 py-2 text-[11px] font-semibold tracking-[0.08em] transition-all duration-200"
              :class="mobileActionClass(item.key)"
              @click="handleNav(item.key)"
            >
              {{ item.label }}
            </button>
          </div>
        </section>

        <div class="workspace-body min-h-0 flex-1 overflow-y-auto xl:overflow-hidden">
          <div class="grid min-h-full grid-cols-1 xl:h-full xl:grid-cols-[minmax(0,1fr)_380px]">
            <main
              class="min-w-0 xl:min-h-0 xl:border-r xl:border-subtle/70"
              :class="effectiveMobilePane === 'learn' ? 'block' : 'hidden xl:block'"
            >
              <ResourceCanvas
                :cards="cards"
                :current-node="currentNode"
                :node-title="nodeTitle"
                :path-nodes="pathNodes"
                :loading="isLoadingNode"
                :overall-progress="overallProgress"
                :mastered-count="masteredCount"
                :get-card-label="getCardLabel"
                :get-agent-label="getAgentLabel"
                :build-quiz="parseQuiz"
                @submit-quiz="(score) => $emit('submit-quiz', score)"
                @select-node="(id) => onSelectNode(id)"
              />
            </main>

            <aside
              class="min-w-0 border-t border-subtle bg-space-surface/50 backdrop-blur-sm xl:min-h-0 xl:border-t-0"
              :class="effectiveMobilePane === 'coach' ? 'block' : 'hidden xl:block'"
            >
              <ChatArea
                :messages="messages"
                :boot-mode="bootMode"
                :probe="probe"
                :probe-collected="probeCollected"
                :probe-total="probeTotal"
                :is-submitting-probe="isSubmittingProbe"
                :busy="isBusy"
                :node-title="nodeTitle"
                :suggestions="coachPrompts"
                @send="handleCoachSend"
                @submit-probe="(values) => $emit('submit-probe', values)"
              />
            </aside>
          </div>
        </div>

        <div class="mobile-dock border-t border-subtle bg-space-panel/85 px-4 py-3 backdrop-blur-xl xl:hidden">
          <div class="flex items-center gap-2 overflow-x-auto">
            <button
              v-for="item in dockActions"
              :key="item.key"
              type="button"
              class="focus-ring shrink-0 rounded-full border px-3.5 py-2 text-[11px] font-semibold tracking-[0.08em] transition-all duration-200"
              :class="mobileActionClass(item.key)"
              @click="handleNav(item.key)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
      </div>

      <SidebarDrawer
        :open="drawerOpen"
        :active-panel="sidebarPanel"
        :nodes="pathNodes"
        :current-node="currentNode"
        :radar-values="capabilityRadar"
        :high-contrast="highContrast"
        :reduce-motion="reduceMotion"
        :font-size="fontSize"
        @select-node="(id) => onSelectNode(id)"
        @toggle-contrast="highContrast = !highContrast"
        @toggle-motion="reduceMotion = !reduceMotion"
        @set-font-size="(size) => fontSize = size"
        @close="drawerOpen = false"
      />

      <transition name="fade">
        <div
          v-if="isBusy || isLoadingNode"
          class="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-space-bg/28 backdrop-blur-[2px]"
        >
          <div class="rounded-[24px] border border-subtle bg-space-panel/95 px-6 py-5 shadow-2xl backdrop-blur-xl">
            <div class="flex items-center gap-4">
              <div class="relative h-10 w-10">
                <div class="absolute inset-0 rounded-full border border-primary/20 animate-spin-slow" />
                <div class="absolute inset-1 rounded-full border-2 border-t-primary border-r-transparent border-b-transparent border-l-transparent animate-spin" />
              </div>
              <div>
                <p class="text-sm font-semibold text-text-primary">{{ loadingTitle }}</p>
                <p class="mt-1 text-[12px] text-text-muted">{{ loadingDetail }}</p>
              </div>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import ChatArea from "./ChatArea.vue";
import IconCheck from "./icons/IconCheck.vue";
import ResourceCanvas from "./ResourceCanvas.vue";
import SidebarDrawer from "./SidebarDrawer.vue";
import SidebarRail from "./SidebarRail.vue";
import TopStatusBar from "./TopStatusBar.vue";

const PREFERENCES_KEY = "eduagent-workspace-preferences";

const props = defineProps({
  bootMode: { type: String, default: "loading" },
  user: { type: Object, default: null },
  currentNode: { type: String, default: "" },
  cards: { type: Array, default: () => [] },
  pathNodes: { type: Array, default: () => [] },
  nodeTitle: { type: String, default: "" },
  messages: { type: Array, default: () => [] },
  capabilityRadar: { type: Array, default: () => [0.5, 0.5, 0.5, 0.5, 0.5] },
  overallProgress: { type: Number, default: 0 },
  masteredCount: { type: Number, default: 0 },
  statuses: { type: Array, default: () => [] },
  infoMessage: { type: String, default: "" },
  isBusy: { type: Boolean, default: false },
  isLoadingNode: { type: Boolean, default: false },
  isSubmittingProbe: { type: Boolean, default: false },
  probe: { type: Object, default: null },
  probeCollected: { type: Number, default: 0 },
  probeTotal: { type: Number, default: 6 },
  getCardLabel: { type: Function, required: true },
  getAgentLabel: { type: Function, required: true },
  parseQuiz: { type: Function, required: true },
  activeCourse: { type: Object, default: null },
  enrolledCourses: { type: Array, default: () => [] },
});

const emit = defineEmits([
  "select-node",
  "submit-quiz",
  "send-tutor",
  "submit-probe",
  "logout",
  "go-home",
  "switch-course",
]);

const drawerOpen = ref(false);
const sidebarPanel = ref("tree");
const courseMenuOpen = ref(false);

const highContrast = ref(false);
const reduceMotion = ref(false);
const fontSize = ref(16);
const mobilePane = ref("learn");

const workspaceNav = [
  { key: "learn", label: "学习区" },
  { key: "coach", label: "辅导区" },
  { key: "path", label: "路径" },
  { key: "assessment", label: "诊断" },
  { key: "settings", label: "设置" },
];

const mobileActions = [
  { key: "learn", label: "学习" },
  { key: "coach", label: "辅导" },
  { key: "path", label: "路径" },
  { key: "assessment", label: "诊断" },
  { key: "settings", label: "设置" },
];

const dockActions = [
  { key: "learn", label: "学习区" },
  { key: "coach", label: "辅导区" },
  { key: "path", label: "路径面板" },
  { key: "settings", label: "设置" },
];

const currentNodeMeta = computed(() =>
  props.pathNodes.find((node) => node.id === props.currentNode),
);

const nextNode = computed(() => {
  const currentIndex = props.pathNodes.findIndex((node) => node.id === props.currentNode);
  if (currentIndex < 0) {
    return props.pathNodes.find((node) => node.mastery < 0.65) ?? null;
  }

  return props.pathNodes.slice(currentIndex + 1).find((node) => node.mastery < 0.65) ?? null;
});

const currentMastery = computed(() =>
  Math.round((currentNodeMeta.value?.mastery ?? 0) * 100),
);

const studyStage = computed(() => {
  if (props.bootMode === "probe") return "入学诊断";
  if (props.isLoadingNode) return "资源生成中";
  if (!props.pathNodes.length) return "路径待生成";
  if (currentMastery.value >= 65) return "节点已达标";
  return "继续学习";
});

const currentNodeCaption = computed(() => {
  if (!props.pathNodes.length) {
    return "等待学习路径";
  }

  const order = currentNodeMeta.value?.order ?? 0;
  return order ? `第 ${order} / ${props.pathNodes.length} 节点` : "当前学习节点";
});

const focusTitle = computed(() => {
  if (props.bootMode === "probe") {
    return "先完成入学诊断，系统再生成个性化路径";
  }

  if (props.isLoadingNode) {
    return "保持当前节点，等待资源矩阵同步完成";
  }

  if (!props.cards.length) {
    return "先装配当前节点的学习资源";
  }

  if (currentMastery.value < 65) {
    return "优先把当前节点学透，再向后推进";
  }

  return nextNode.value ? `准备推进到下一薄弱节点：${nextNode.value.title}` : "当前主路径已接近完成";
});

const focusDetail = computed(() => {
  if (props.bootMode === "probe") {
    return "诊断结果会决定学习起点、资源密度和后续节点顺序，先完成它比直接开始更有效率。";
  }

  if (props.isLoadingNode) {
    return "资源生成阶段不建议频繁切换节点，等待概念、代码、练习和诊断全部落位后再继续。";
  }

  if (!props.cards.length) {
    return "系统会围绕当前节点生成成体系的学习材料，避免知识点孤立出现。";
  }

  if (currentMastery.value < 65) {
    return "建议按概念理解、代码示例、互动练习、诊断测评的顺序推进，减少学习跳读。";
  }

  return nextNode.value
    ? "当前节点已接近达标，可以在完成本轮诊断后切换到下一个薄弱点。"
    : "主要薄弱点已被覆盖，接下来更适合做复盘、串联和面试化练习。";
});

const learningSequenceTitle = computed(() => (
  props.cards.length
    ? "推荐顺序：概念 -> 代码 -> 练习 -> 诊断"
    : "等待资源装配后自动生成学习顺序"
));

const learningSequenceDetail = computed(() => (
  props.cards.length
    ? "这一顺序更接近真实学习网站的内容编排逻辑，能先建立认知骨架，再进入操作与验证。"
    : "当节点资源生成完成后，矩阵会自动排列为适合连续学习的顺序。"
));

const assistantMessageCount = computed(() =>
  props.messages.filter((message) => message.role === "assistant").length,
);

const metrics = computed(() => [
  {
    label: "总进度",
    value: `${props.overallProgress}%`,
    detail: `${props.masteredCount}/${props.pathNodes.length || 0} 节点达标`,
  },
  {
    label: "当前掌握",
    value: `${currentMastery.value}%`,
    detail: currentNodeMeta.value ? "会根据诊断结果动态更新" : "等待选择节点",
  },
  {
    label: "资源状态",
    value: props.cards.length ? `${props.cards.length}` : "0",
    detail: props.cards.length ? "学习材料已装配" : "等待生成",
  },
  {
    label: "辅导对话",
    value: `${assistantMessageCount.value}`,
    detail: assistantMessageCount.value ? "当前会话已有辅导反馈" : "尚未发起追问",
  },
]);

const compactStatuses = computed(() =>
  props.statuses.slice(0, 3).map((status) => ({
    ...status,
    panelClass: status.progress === 100
      ? "border-success/20"
      : status.active
        ? "border-primary/20"
        : "border-subtle",
  })),
);

const coachPrompts = computed(() => {
  const nodeLabel = props.nodeTitle || "当前知识点";
  return [
    `帮我梳理 ${nodeLabel} 的核心概念`,
    `比较 ${nodeLabel} 和上一节点的关系`,
    `给我一道围绕 ${nodeLabel} 的面试题`,
    `告诉我当前节点最容易犯的错误`,
  ];
});

const effectiveMobilePane = computed(() => (
  props.bootMode === "probe" ? "coach" : mobilePane.value
));

const loadingTitle = computed(() => (
  props.isLoadingNode ? "正在装配当前节点的学习资源" : "正在同步工作台状态"
));

const loadingDetail = computed(() => (
  props.isLoadingNode
    ? "系统会按当前节点生成概念、代码、练习与诊断内容。"
    : "请稍候，数据和会话状态正在对齐。"
));

watch(
  () => props.bootMode,
  (mode) => {
    if (mode === "probe") {
      mobilePane.value = "coach";
    }
  },
  { immediate: true },
);

watch(
  [highContrast, reduceMotion, fontSize],
  ([nextContrast, nextMotion, nextFont]) => {
    if (typeof window === "undefined") {
      return;
    }

    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({
      highContrast: nextContrast,
      reduceMotion: nextMotion,
      fontSize: nextFont,
    }));
  },
);

onMounted(() => {
  if (typeof window === "undefined") {
    return;
  }

  try {
    const raw = window.localStorage.getItem(PREFERENCES_KEY);
    if (!raw) {
      return;
    }

    const saved = JSON.parse(raw);
    highContrast.value = Boolean(saved.highContrast);
    reduceMotion.value = Boolean(saved.reduceMotion);
    fontSize.value = typeof saved.fontSize === "number" ? saved.fontSize : 16;
  } catch {
    highContrast.value = false;
    reduceMotion.value = false;
    fontSize.value = 16;
  }
});

function onSidebarSelect(panelKey) {
  if (sidebarPanel.value === panelKey && drawerOpen.value) {
    drawerOpen.value = false;
  } else {
    sidebarPanel.value = panelKey;
    drawerOpen.value = true;
  }
}

function openPanel(panelKey) {
  sidebarPanel.value = panelKey;
  drawerOpen.value = true;
}

function onSelectNode(nodeId) {
  emit("select-node", nodeId);
  drawerOpen.value = false;
  mobilePane.value = "learn";
}

function onSwitchCourse(courseId) {
  courseMenuOpen.value = false;
  emit("switch-course", courseId);
}

function handleCoachSend(message) {
  mobilePane.value = "coach";
  emit("send-tutor", message);
}

function handleNav(key) {
  if (key === "learn") {
    mobilePane.value = "learn";
    drawerOpen.value = false;
    return;
  }

  if (key === "coach") {
    mobilePane.value = "coach";
    drawerOpen.value = false;
    return;
  }

  if (key === "path") {
    openPanel("tree");
    return;
  }

  if (key === "assessment") {
    openPanel("radar");
    return;
  }

  if (key === "settings") {
    openPanel("settings");
  }
}

function navButtonClass(key) {
  if ((key === "learn" || key === "coach") && effectiveMobilePane.value === key) {
    return "bg-primary-soft text-primary";
  }

  if (key === "path" && drawerOpen.value && sidebarPanel.value === "tree") {
    return "bg-primary-soft text-primary";
  }

  if (key === "assessment" && drawerOpen.value && sidebarPanel.value === "radar") {
    return "bg-primary-soft text-primary";
  }

  if (key === "settings" && drawerOpen.value && sidebarPanel.value === "settings") {
    return "bg-primary-soft text-primary";
  }

  return "text-text-muted hover:bg-card-hover hover:text-text-secondary";
}

function mobileActionClass(key) {
  const active =
    (key === "learn" || key === "coach")
      ? effectiveMobilePane.value === key
      : (key === "path" && drawerOpen.value && sidebarPanel.value === "tree")
        || (key === "assessment" && drawerOpen.value && sidebarPanel.value === "radar")
        || (key === "settings" && drawerOpen.value && sidebarPanel.value === "settings");

  return active
    ? "border-primary/25 bg-primary-soft text-primary"
    : "border-subtle bg-card text-text-muted";
}
</script>

<style scoped>
.workspace-shell.is-high-contrast {
  filter: contrast(1.06) saturate(1.03);
}

.workspace-shell.is-reduced-motion,
.workspace-shell.is-reduced-motion * {
  animation-duration: 0.01ms !important;
  animation-iteration-count: 1 !important;
  scroll-behavior: auto !important;
  transition-duration: 0.01ms !important;
}

.workspace-body {
  padding-bottom: calc(env(safe-area-inset-bottom, 0px) + 84px);
}

.mobile-dock {
  padding-bottom: calc(env(safe-area-inset-bottom, 0px) + 0.75rem);
}

@media (min-width: 1280px) {
  .workspace-body {
    padding-bottom: 0;
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 220ms ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
