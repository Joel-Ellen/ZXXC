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

    <div
      class="workspace-pane-layout relative min-h-0 flex-1"
      :class="{ 'is-tutor-collapsed': isTutorCollapsed }"
    >
      <LearningPane
        ref="learnPanelRef"
        class="workspace-pane-layout__pane workspace-pane-layout__learning"
        :class="{ 'is-active-mobile': effectiveMobilePane === 'learn' }"
        panel-id="workspace-learn-panel"
        :session-id="sessionId"
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
        @quiz-next="onQuizNext"
        @select-node="(id) => onSelectNode(id)"
        @refresh="$emit('refresh-resources')"
        @generate-card="(payload) => $emit('generate-card', payload)"
        @filter-change="onResourceFilterChange"
        @code-run="(payload) => $emit('code-run', payload)"
        @code-submitted="(payload) => $emit('code-submitted', payload)"
      />

      <button
        v-if="isTutorCollapsed"
        type="button"
        class="desktop-tutor-toggle focus-ring"
        aria-controls="workspace-coach-panel"
        aria-expanded="false"
        @click="openTutor"
      >
        <IconChat :size="17" aria-hidden="true" />
        <span>展开辅导</span>
      </button>

      <TutorPane
        ref="coachPanelRef"
        class="workspace-pane-layout__pane workspace-pane-layout__tutor"
        :class="{ 'is-active-mobile': effectiveMobilePane === 'coach' }"
        :aria-hidden="isTutorCollapsed ? 'true' : undefined"
        panel-id="workspace-coach-panel"
        :current-node-title="nodeTitle"
        :messages="messages"
        :boot-mode="bootMode"
        :probe="probe"
        :probe-collected="probeCollected"
        :probe-total="probeTotal"
        :is-submitting-probe="isSubmittingProbe"
        :busy="isBusy"
        :suggestions="coachPrompts"
        :collapsible="isDesktopViewport && bootMode !== 'probe'"
        @send="handleCoachSend"
        @submit-probe="(values) => $emit('submit-probe', values)"
        @collapse="collapseTutor"
      />

      <nav class="mobile-dock sticky bottom-0 z-20 border-t border-subtle bg-space-panel/88 px-3 py-2 backdrop-blur-xl" aria-label="工作台切换">
        <div class="mobile-dock__actions">
          <button
            v-for="item in dockActions"
            :key="item.key"
            type="button"
            class="focus-ring min-h-11 min-w-0 rounded-xl border px-2 py-2 text-[11px] font-semibold transition-all duration-200"
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
        :feedback-items="agentFeedback"
        :last-diagnostic="lastDiagnostic"
        :current-node-title="nodeTitle"
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import SidebarDrawer from "./SidebarDrawer.vue";
import IconChat from "./icons/IconChat.vue";
import LearningPane from "./workspace/LearningPane.vue";
import SessionHeader from "./workspace/SessionHeader.vue";
import TutorPane from "./workspace/TutorPane.vue";
import WorkspaceShell from "./workspace/WorkspaceShell.vue";

const PREFERENCES_KEY = "eduagent-workspace-preferences";
const LEARN_PANEL_ID = "workspace-learn-panel";
const router = useRouter();
const COACH_PANEL_ID = "workspace-coach-panel";
const DRAWER_PANEL_ID = "workspace-sidebar-drawer";

const props = defineProps({
  bootMode: { type: String, default: "loading" },
  user: { type: Object, default: null },
  sessionId: { type: String, default: "" },
  currentNode: { type: String, default: "" },
  cards: { type: Array, default: () => [] },
  pathNodes: { type: Array, default: () => [] },
  nodeTitle: { type: String, default: "" },
  messages: { type: Array, default: () => [] },
  agentFeedback: { type: Array, default: () => [] },
  capabilityRadar: { type: Array, default: () => [0.5, 0.5, 0.5, 0.5, 0.5] },
  overallProgress: { type: Number, default: 0 },
  masteredCount: { type: Number, default: 0 },
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
  "code-run",
  "code-submitted",
  "restart-probe",
  "browse-courses",
]);

const WORKSPACE_VIEWS = new Set(["study", "path", "agents", "evidence"]);
const WORKSPACE_DRAWER_PANELS = {
  path: "tree",
  agents: "feedback",
  evidence: "radar",
};
const drawerOpen = ref(false);
const sidebarPanel = ref("all");
const activeResourceCategory = ref("all");
const learnPanelRef = ref(null);
const coachPanelRef = ref(null);

const highContrast = ref(false);
const reduceMotion = ref(false);
const fontSize = ref(16);
const mobilePane = ref("learn");
const tutorCollapsed = ref(true);
const isDesktopViewport = ref(false);
let desktopMediaQuery = null;
const isWorkspaceBusy = computed(() => props.isBusy || props.isLoadingNode);
const isTutorCollapsed = computed(() => (
  isDesktopViewport.value && tutorCollapsed.value && props.bootMode !== "probe"
));

const workspaceNav = [
  { key: "study", label: "学习工作台" },
  { key: "path", label: "学习路径" },
  { key: "agents", label: "智能体协同" },
  { key: "evidence", label: "学习成果" },
  { key: "review", label: "错题复习" },
];

const dockActions = [
  { key: "study", label: "学习" },
  { key: "coach", label: "辅导" },
  { key: "path", label: "路径" },
  { key: "agents", label: "协同" },
  { key: "evidence", label: "成果" },
];

const workspaceNavItems = computed(() =>
  workspaceNav.map((item) => ({
    ...item,
    active: isWorkspaceNavActive(item.key),
    expanded: item.key !== "study" ? String(isWorkspaceNavActive(item.key)) : undefined,
    hasPopup: item.key !== "study",
    targetId: item.key === "study" ? LEARN_PANEL_ID : DRAWER_PANEL_ID,
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
  [highContrast, reduceMotion, fontSize, tutorCollapsed],
  ([nextContrast, nextMotion, nextFont, nextTutorCollapsed]) => {
    if (typeof window === "undefined") {
      return;
    }

    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({
      highContrast: nextContrast,
      reduceMotion: nextMotion,
      fontSize: nextFont,
      tutorCollapsed: nextTutorCollapsed,
      tutorPreferenceSet: true,
      motionPreferenceSet: true,
    }));
  },
);

onMounted(() => {
  if (typeof window === "undefined") {
    return;
  }

  desktopMediaQuery = window.matchMedia("(min-width: 1100px)");
  updateDesktopViewport(desktopMediaQuery);
  desktopMediaQuery.addEventListener?.("change", updateDesktopViewport);

  try {
    const raw = window.localStorage.getItem(PREFERENCES_KEY);
    if (!raw) {
      return;
    }

    const saved = JSON.parse(raw);
    highContrast.value = Boolean(saved.highContrast);
    reduceMotion.value = saved.motionPreferenceSet === true
      ? Boolean(saved.reduceMotion)
      : false;
    fontSize.value = typeof saved.fontSize === "number" ? saved.fontSize : 16;
    tutorCollapsed.value = saved.tutorPreferenceSet === true
      ? Boolean(saved.tutorCollapsed)
      : true;
  } catch {
    highContrast.value = false;
    reduceMotion.value = false;
    fontSize.value = 16;
    tutorCollapsed.value = true;
  }
});

onBeforeUnmount(() => {
  desktopMediaQuery?.removeEventListener?.("change", updateDesktopViewport);
});

function updateDesktopViewport(event) {
  isDesktopViewport.value = Boolean(event.matches);
}

function onResourceFilterChange(filterKey) {
  activeResourceCategory.value = filterKey;
  sidebarPanel.value = filterKey;
}

function onSidebarSelect(panelKey) {
  if (panelKey === "probe") {
    emit("restart-probe");
    return;
  }

  // Content category keys → update filter, close drawer
  const CONTENT_KEYS = new Set(["concept", "code", "practice", "video", "quiz", "all"]);
  if (CONTENT_KEYS.has(panelKey)) {
    activeResourceCategory.value = panelKey;
    sidebarPanel.value = panelKey;
    drawerOpen.value = false;
    return;
  }
  if (panelKey === "tree") {
    openPanel("tree");
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

function onQuizNext(payload) {
  const nodeId = typeof payload === "string" ? payload : payload?.nodeId;
  if (!nodeId) return;

  activeResourceCategory.value = "all";
  sidebarPanel.value = "all";
  onSelectNode(nodeId);
}

function onSwitchCourse(courseId) {
  emit("switch-course", courseId);
}

function handleBrowseCourses() {
  emit("browse-courses");
}

function handleCoachSend(message) {
  mobilePane.value = "coach";
  emit("send-tutor", message);
}

async function openTutor() {
  tutorCollapsed.value = false;
  drawerOpen.value = false;
  await focusWorkspaceRegion("coach");
}

async function collapseTutor() {
  if (props.bootMode === "probe") {
    return;
  }

  tutorCollapsed.value = true;
  await focusWorkspaceRegion("learn");
}

async function handleNav(key) {
  if (key === "review") {
    router.push("/review");
    return;
  }
  if (WORKSPACE_VIEWS.has(key)) {
    if (key !== "study") {
      const panelKey = WORKSPACE_DRAWER_PANELS[key];
      if (drawerOpen.value && sidebarPanel.value === panelKey) {
        drawerOpen.value = false;
      } else {
        openPanel(panelKey);
      }
      mobilePane.value = "learn";
      return;
    }

    mobilePane.value = "learn";
    drawerOpen.value = false;
    await focusWorkspaceRegion("learn");
    return;
  }

  if (key === "coach") {
    if (isDesktopViewport.value) {
      if (props.bootMode === "probe") {
        await openTutor();
        return;
      }

      if (tutorCollapsed.value) {
        await openTutor();
      } else {
        await collapseTutor();
      }
      return;
    }

    mobilePane.value = "coach";
    drawerOpen.value = false;
    await focusWorkspaceRegion("coach");
    return;
  }

  if (key === "assessment") {
    openPanel("radar");
    return;
  }

  if (key === "feedback") {
    openPanel("feedback");
    return;
  }

  if (key === "settings") {
    openPanel("settings");
    return;
  }

  if (key === "probe") {
    emit("restart-probe");
  }
}

function isDrawerAction(key) {
  return key === "path" || key === "agents" || key === "evidence" || key === "settings";
}

function isNavActive(key) {
  if (WORKSPACE_VIEWS.has(key)) {
    return isWorkspaceNavActive(key);
  }

  if (isDesktopViewport.value) {
    if (key === "learn") {
      return true;
    }

    if (key === "coach") {
      return !isTutorCollapsed.value;
    }
  }

  if (key === "learn" || key === "coach") {
    return effectiveMobilePane.value === key;
  }

  if (key === "path") {
    return drawerOpen.value && sidebarPanel.value === "tree";
  }

  if (key === "assessment") {
    return drawerOpen.value && sidebarPanel.value === "radar";
  }

  if (key === "feedback") {
    return drawerOpen.value && sidebarPanel.value === "feedback";
  }

  if (key === "settings") {
    return drawerOpen.value && sidebarPanel.value === "settings";
  }

  return false;
}

function isWorkspaceNavActive(key) {
  if (key === "study") {
    return !drawerOpen.value || !Object.values(WORKSPACE_DRAWER_PANELS).includes(sidebarPanel.value);
  }

  return drawerOpen.value && sidebarPanel.value === WORKSPACE_DRAWER_PANELS[key];
}

function navTargetId(key) {
  if (key === "probe") {
    return undefined;
  }

  if (key === "learn" || key === "study") {
    return LEARN_PANEL_ID;
  }

  if (key === "coach") {
    return COACH_PANEL_ID;
  }

  return DRAWER_PANEL_ID;
}

function navExpandedState(key) {
  if (key === "coach" && isDesktopViewport.value) {
    return String(!isTutorCollapsed.value);
  }

  if (!isDrawerAction(key)) {
    return undefined;
  }

  return String(isNavActive(key));
}

async function focusWorkspaceRegion(key) {
  if (typeof window === "undefined" || !window.matchMedia("(min-width: 1100px)").matches) {
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

  return paneElement.querySelector(".resource-canvas")
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

.mobile-dock__actions {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.4rem;
}

.desktop-tutor-toggle {
  display: none;
}

@media (min-width: 1100px) {
  .workspace-pane-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(19rem, 20.5rem);
    gap: 0.5rem;
    padding: 0 1rem 1rem;
    transition: grid-template-columns 320ms var(--ease-emphasized);
  }

  .workspace-pane-layout__pane,
  .workspace-pane-layout__pane.is-active-mobile {
    display: flex;
    min-width: 0;
    min-height: 0;
  }

  .workspace-pane-layout.is-tutor-collapsed {
    grid-template-columns: minmax(0, 1fr) minmax(0, 0);
  }

  .workspace-pane-layout__tutor {
    transform-origin: right center;
    transition:
      opacity 180ms var(--ease-standard),
      transform 260ms var(--ease-emphasized),
      visibility 0s linear 0s;
  }

  .workspace-pane-layout.is-tutor-collapsed .workspace-pane-layout__tutor {
    visibility: hidden;
    pointer-events: none;
    opacity: 0;
    transform: translateX(14px) scale(0.985);
    transition:
      opacity 140ms var(--ease-standard),
      transform 220ms var(--ease-emphasized),
      visibility 0s linear 220ms;
  }

  .desktop-tutor-toggle {
    position: absolute;
    top: 50%;
    right: 1rem;
    z-index: var(--z-sticky);
    display: inline-flex;
    min-height: 2.75rem;
    align-items: center;
    gap: 0.45rem;
    transform: translateY(-50%);
    border: 1px solid var(--color-primary);
    border-radius: var(--radius-sm) 0 0 var(--radius-sm);
    background: var(--space-panel);
    padding: 0 0.8rem;
    color: var(--color-primary-dark);
    font-size: 0.75rem;
    font-weight: 750;
    transition:
      background-color var(--duration-fast) var(--ease-standard),
      color var(--duration-fast) var(--ease-standard);
  }

  .desktop-tutor-toggle:hover {
    background: var(--color-primary-soft);
    color: var(--text-primary);
  }

  .mobile-dock {
    display: none;
  }
}

@media (max-width: 359px) {
  .mobile-dock {
    padding-inline: 0.4rem;
  }

  .mobile-dock__actions {
    gap: 0.25rem;
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
