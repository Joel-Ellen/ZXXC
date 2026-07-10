<template>
  <WorkspaceShell
    :path-nodes="pathNodes"
    :active-panel="sidebarPanel"
    :drawer-open="drawerOpen"
    panel-id="workspace-sidebar-drawer"
    :high-contrast="highContrast"
    :reduce-motion="reduceMotion"
    :font-size="fontSize"
    :busy="isWorkspaceBusy"
    @select-panel="onSidebarSelect"
    @workspace-wheel="forwardWorkspaceWheel"
  >
    <template #header>
      <SessionHeader
        :user="user"
        :active-course="activeCourse"
        :enrolled-courses="enrolledCourses"
        :boot-mode="bootMode"
        :node-title="nodeTitle"
        :current-node="currentNode"
        :path-nodes="pathNodes"
        :cards="cards"
        :overall-progress="overallProgress"
        :mastered-count="masteredCount"
        :info-message="infoMessage"
        :is-busy="isBusy"
        :is-loading-node="isLoadingNode"
        :navigation="workspaceNavItems"
        @switch-course="onSwitchCourse"
        @browse-courses="handleBrowseCourses"
        @go-home="$emit('go-home')"
        @logout="$emit('logout')"
        @navigate="handleNav"
      />
    </template>

    <div class="workspace-pane-layout relative min-h-0 flex-1">
      <LearningPane
        ref="learnPanelRef"
        class="workspace-pane-layout__pane workspace-pane-layout__learning"
        :class="{ 'is-active-mobile': effectiveMobilePane === 'learn' }"
        panel-id="workspace-learn-panel"
        :cards="cards"
        :current-node="currentNode"
        :node-title="nodeTitle"
        :path-nodes="pathNodes"
        :loading="isLoadingNode"
        :overall-progress="overallProgress"
        :mastered-count="masteredCount"
        :last-diagnostic="lastDiagnostic"
        :filter-type="activeResourceCategory"
        :get-card-label="getCardLabel"
        :get-agent-label="getAgentLabel"
        :build-quiz="parseQuiz"
        @submit-quiz="(score) => $emit('submit-quiz', score)"
        @select-node="(id) => onSelectNode(id)"
        @refresh="$emit('refresh-resources')"
        @generate-card="(payload) => $emit('generate-card', payload)"
      />

      <TutorPane
        ref="coachPanelRef"
        class="workspace-pane-layout__pane workspace-pane-layout__tutor"
        :class="{ 'is-active-mobile': effectiveMobilePane === 'coach' }"
        panel-id="workspace-coach-panel"
        :feedback-items="agentFeedback"
        :last-diagnostic="lastDiagnostic"
        :current-node-title="nodeTitle"
        :messages="messages"
        :boot-mode="bootMode"
        :probe="probe"
        :probe-collected="probeCollected"
        :probe-total="probeTotal"
        :is-submitting-probe="isSubmittingProbe"
        :busy="isBusy"
        :suggestions="coachPrompts"
        @send="handleCoachSend"
        @submit-probe="(values) => $emit('submit-probe', values)"
      />

      <nav class="mobile-dock sticky bottom-0 z-20 border-t border-subtle bg-space-panel/88 px-4 py-3 backdrop-blur-xl xl:hidden" aria-label="工作台切换">
        <div class="flex items-center gap-2 overflow-x-auto">
          <button
            v-for="item in dockActions"
            :key="item.key"
            type="button"
            class="focus-ring shrink-0 rounded-full border px-3.5 py-2 text-[11px] font-semibold tracking-[0.08em] transition-all duration-200"
            :class="mobileActionClass(item.key)"
            :aria-controls="navTargetId(item.key)"
            :aria-expanded="navExpandedState(item.key)"
            :aria-haspopup="isDrawerAction(item.key) ? 'dialog' : undefined"
            :aria-pressed="String(isNavActive(item.key))"
            @click="handleNav(item.key)"
          >
            {{ item.label }}
          </button>
        </div>
      </nav>
    </div>

    <template #drawer>
      <SidebarDrawer
        :open="drawerOpen"
        :active-panel="sidebarPanel"
        panel-id="workspace-sidebar-drawer"
        :nodes="pathNodes"
        :current-node="currentNode"
        :radar-values="capabilityRadar"
        :high-contrast="highContrast"
        :reduce-motion="reduceMotion"
        :font-size="fontSize"
        @select-node="(id) => onSelectNode(id)"
        @switch-panel="onDrawerPanelSwitch"
        @toggle-contrast="highContrast = !highContrast"
        @toggle-motion="reduceMotion = !reduceMotion"
        @set-font-size="(size) => fontSize = size"
        @close="drawerOpen = false"
      />
    </template>

    <template #overlay>
      <transition name="fade">
        <div
          v-if="isBusy || isLoadingNode"
          class="pointer-events-auto absolute inset-0 z-30 flex items-center justify-center bg-space-bg/28 backdrop-blur-[2px]"
          role="status"
          aria-live="polite"
          aria-atomic="true"
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
    </template>
  </WorkspaceShell>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import SidebarDrawer from "./SidebarDrawer.vue";
import LearningPane from "./workspace/LearningPane.vue";
import SessionHeader from "./workspace/SessionHeader.vue";
import TutorPane from "./workspace/TutorPane.vue";
import WorkspaceShell from "./workspace/WorkspaceShell.vue";

const PREFERENCES_KEY = "eduagent-workspace-preferences";
const LEARN_PANEL_ID = "workspace-learn-panel";
const COACH_PANEL_ID = "workspace-coach-panel";
const DRAWER_PANEL_ID = "workspace-sidebar-drawer";

const props = defineProps({
  bootMode: { type: String, default: "loading" },
  user: { type: Object, default: null },
  currentNode: { type: String, default: "" },
  cards: { type: Array, default: () => [] },
  pathNodes: { type: Array, default: () => [] },
  nodeTitle: { type: String, default: "" },
  messages: { type: Array, default: () => [] },
  agentFeedback: { type: Array, default: () => [] },
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
  lastDiagnostic: { type: Object, default: null },
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
  "refresh-resources",
  "generate-card",
]);

const drawerOpen = ref(false);
const sidebarPanel = ref("concept");
const activeResourceCategory = ref("concept"); // which content type is active
const learnPanelRef = ref(null);
const coachPanelRef = ref(null);

const highContrast = ref(false);
const reduceMotion = ref(false);
const fontSize = ref(16);
const mobilePane = ref("learn");
const isWorkspaceBusy = computed(() => props.isBusy || props.isLoadingNode);

const workspaceNav = [
  { key: "learn", label: "学习区" },
  { key: "coach", label: "辅导区" },
  { key: "path", label: "路径" },
  { key: "assessment", label: "诊断" },
  { key: "settings", label: "设置" },
];

const dockActions = [
  { key: "learn", label: "学习" },
  { key: "coach", label: "辅导" },
  { key: "path", label: "路径" },
  { key: "assessment", label: "诊断" },
  { key: "settings", label: "设置" },
];

const workspaceNavItems = computed(() =>
  workspaceNav.map((item) => ({
    ...item,
    active: isNavActive(item.key),
    expanded: navExpandedState(item.key),
    hasPopup: isDrawerAction(item.key),
    targetId: navTargetId(item.key),
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
  // Content category keys → update filter, close drawer
  const CONTENT_KEYS = new Set(["concept", "code", "practice", "video", "quiz", "all"]);
  if (CONTENT_KEYS.has(panelKey)) {
    activeResourceCategory.value = panelKey;
    sidebarPanel.value = panelKey;
    drawerOpen.value = false;
    return;
  }
  // Drawer keys (tree, radar, settings)
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

function onDrawerPanelSwitch(panelKey) {
  openPanel(panelKey);
}

function onSelectNode(nodeId) {
  emit("select-node", nodeId);
  drawerOpen.value = false;
  mobilePane.value = "learn";
}

function onSwitchCourse(courseId) {
  emit("switch-course", courseId);
}

function handleBrowseCourses() {
  emit("go-home");
}

function handleCoachSend(message) {
  mobilePane.value = "coach";
  emit("send-tutor", message);
}

async function handleNav(key) {
  if (key === "learn") {
    mobilePane.value = "learn";
    drawerOpen.value = false;
    await focusWorkspaceRegion("learn");
    return;
  }

  if (key === "coach") {
    mobilePane.value = "coach";
    drawerOpen.value = false;
    await focusWorkspaceRegion("coach");
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

function isDrawerAction(key) {
  return key === "path" || key === "assessment" || key === "settings";
}

function isNavActive(key) {
  if (key === "learn" || key === "coach") {
    return effectiveMobilePane.value === key;
  }

  if (key === "path") {
    return drawerOpen.value && sidebarPanel.value === "tree";
  }

  if (key === "assessment") {
    return drawerOpen.value && sidebarPanel.value === "radar";
  }

  if (key === "settings") {
    return drawerOpen.value && sidebarPanel.value === "settings";
  }

  return false;
}

function navTargetId(key) {
  if (key === "learn") {
    return LEARN_PANEL_ID;
  }

  if (key === "coach") {
    return COACH_PANEL_ID;
  }

  return DRAWER_PANEL_ID;
}

function navExpandedState(key) {
  if (!isDrawerAction(key)) {
    return undefined;
  }

  return String(isNavActive(key));
}

async function focusWorkspaceRegion(key) {
  if (typeof window === "undefined" || !window.matchMedia("(min-width: 1280px)").matches) {
    return;
  }

  await nextTick();
  const target = key === "coach" ? coachPanelRef.value : learnPanelRef.value;
  if (typeof target?.focus === "function") {
    target.focus();
    return;
  }

  const targetElement = resolvePaneElement(target);
  if (targetElement) {
    targetElement.focus({ preventScroll: true });
  }
}

function mobileActionClass(key) {
  return isNavActive(key)
    ? "border-primary/25 bg-primary-soft text-primary"
    : "border-subtle bg-card text-text-muted";
}

function forwardWorkspaceWheel(event) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  if (target.closest("textarea, input, select, [contenteditable='true']")) {
    return;
  }

  if (target.closest(`#${LEARN_PANEL_ID}, #${COACH_PANEL_ID}, #${DRAWER_PANEL_ID}`)) {
    return;
  }

  const paneKey = effectiveMobilePane.value === "coach" ? "coach" : "learn";
  const activePanelRef = paneKey === "coach" ? coachPanelRef.value : learnPanelRef.value;
  const activePanel = resolvePaneElement(activePanelRef);
  if (!activePanel) {
    return;
  }

  const scrollCandidate = findPrimaryScrollTarget(activePanel, paneKey);
  if (!(scrollCandidate instanceof HTMLElement)) {
    return;
  }

  scrollCandidate.scrollTop += event.deltaY;
}

function findPrimaryScrollTarget(paneElement, paneKey) {
  if (paneKey === "coach") {
    return paneElement.querySelector("[data-chat-scroll='true']");
  }

  return paneElement.querySelector(".resource-canvas > .aurora-scroll")
    ?? paneElement.querySelector(".aurora-scroll");
}

function resolvePaneElement(target) {
  if (target instanceof HTMLElement) {
    return target;
  }

  if (typeof target?.getElement === "function") {
    const element = target.getElement();
    return element instanceof HTMLElement ? element : null;
  }

  return null;
}
</script>

<style scoped>
.workspace-pane-layout {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.workspace-pane-layout__pane {
  display: none;
}

.workspace-pane-layout__pane.is-active-mobile {
  display: flex;
  flex: 1;
}

.mobile-dock {
  z-index: 40;
  background: var(--space-panel);
  box-shadow: 0 -10px 24px rgba(15, 23, 42, 0.08);
  padding-bottom: calc(env(safe-area-inset-bottom, 0px) + 0.75rem);
}

@media (min-width: 1280px) {
  .workspace-pane-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(22rem, 26rem);
    gap: 0.75rem;
    padding: 0 1rem 1rem;
  }

  .workspace-pane-layout__pane,
  .workspace-pane-layout__pane.is-active-mobile {
    display: flex;
    min-width: 0;
    min-height: 0;
  }

  .mobile-dock {
    display: none;
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--duration-base) var(--ease-standard);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
