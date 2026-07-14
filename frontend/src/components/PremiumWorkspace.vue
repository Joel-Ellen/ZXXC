<template>
  <WorkspaceShell
    :path-nodes="pathNodes"
    :current-node="currentNode"
    :high-contrast="highContrast"
    :reduce-motion="reduceMotion"
    :font-size="fontSize"
    :busy="isWorkspaceBusy"
    @select-node="onSelectNode"
    @workspace-wheel="forwardWorkspaceWheel"
  >
    <template #header>
      <SessionHeader
        :active-course="activeCourse"
        :enrolled-courses="enrolledCourses"
        :node-title="nodeTitle"
        :current-node="currentNode"
        :path-nodes="pathNodes"
        :overall-progress="overallProgress"
        :mastered-count="masteredCount"
        :info-message="infoMessage"
        :tutor-collapsed="tutorCollapsed"
        @switch-course="onSwitchCourse"
        @browse-courses="handleBrowseCourses"
        @toggle-tutor="toggleTutor"
        @navigate="(key) => $emit('navigate', key)"
      />
    </template>

    <div class="workspace-pane-layout relative min-h-0 flex-1" :class="{ 'has-collapsed-tutor': tutorCollapsed }">
      <LearningPane
        ref="learnPanelRef"
        class="workspace-pane-layout__pane workspace-pane-layout__learning"
        :class="{ 'is-active-mobile': effectiveMobilePane === 'learn' }"
        panel-id="workspace-learn-panel"
        :cards="cards"
        :session-id="sessionId"
        :current-node="currentNode"
        :node-title="nodeTitle"
        :path-nodes="pathNodes"
        :loading="isLoadingNode"
        :overall-progress="overallProgress"
        :mastered-count="masteredCount"
        :last-diagnostic="lastDiagnostic"
        :focus-card-type="focusCardType"
        :review-item-id="reviewItemId"
        :review-phase="reviewPhase"
        :filter-type="activeResourceCategory"
        :get-card-label="getCardLabel"
        :get-agent-label="getAgentLabel"
        :build-quiz="parseQuiz"
        @submit-quiz="(score) => $emit('submit-quiz', score)"
        @select-node="(id) => onSelectNode(id)"
        @refresh="$emit('refresh-resources')"
        @generate-card="(payload) => $emit('generate-card', payload)"
        @content-viewed="(payload) => $emit('content-viewed', payload)"
        @hint-requested="(payload) => $emit('hint-requested', payload)"
        @answer-selected="(payload) => $emit('answer-selected', payload)"
        @code-run="(payload) => $emit('code-run', payload)"
        @code-submitted="(payload) => $emit('code-submitted', payload)"
        @open-review="$emit('open-review')"
        @prepare-review-retest="(itemId) => $emit('prepare-review-retest', itemId)"
      />

      <TutorPane
        ref="coachPanelRef"
        class="workspace-pane-layout__pane workspace-pane-layout__tutor"
        :class="{
          'is-active-mobile': effectiveMobilePane === 'coach',
          'is-collapsed-desktop': tutorCollapsed,
        }"
        panel-id="workspace-coach-panel"
        :feedback-items="agentFeedback"
        :last-diagnostic="lastDiagnostic"
        :current-node-title="nodeTitle"
        :current-node="currentNode"
        :session-id="sessionId"
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

      <nav
        v-if="bootMode !== 'probe'"
        class="mobile-dock sticky bottom-0 z-20 border-t border-subtle xl:hidden"
        aria-label="学习工作区切换"
      >
        <div class="mobile-dock__actions">
          <button
            v-for="item in dockActions"
            :key="item.key"
            type="button"
            class="focus-ring mobile-dock__action"
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
        panel-id="workspace-sidebar-drawer"
        :nodes="pathNodes"
        :current-node="currentNode"
        @select-node="(id) => onSelectNode(id)"
        @close="closeDrawer"
      />
    </template>

    <template #overlay>
      <transition name="fade">
        <div
          v-if="isBusy || isLoadingNode"
          class="pointer-events-auto absolute inset-0 z-30 flex items-center justify-center bg-space-bg"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          <div class="rounded-lg border border-subtle bg-space-panel px-6 py-5">
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
  sessionId: { type: String, default: "" },
  currentNode: { type: String, default: "" },
  cards: { type: Array, default: () => [] },
  pathNodes: { type: Array, default: () => [] },
  nodeTitle: { type: String, default: "" },
  messages: { type: Array, default: () => [] },
  agentFeedback: { type: Array, default: () => [] },
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
  focusCardType: { type: String, default: "" },
  reviewItemId: { type: String, default: "" },
  reviewPhase: { type: String, default: "" },
  getCardLabel: { type: Function, required: true },
  getAgentLabel: { type: Function, required: true },
  parseQuiz: { type: Function, required: true },
  activeCourse: { type: Object, default: null },
  enrolledCourses: { type: Array, default: () => [] },
  learningView: { type: String, default: "learn" },
});

const emit = defineEmits([
  "select-node",
  "submit-quiz",
  "send-tutor",
  "submit-probe",
  "logout",
  "browse-courses",
  "switch-course",
  "refresh-resources",
  "generate-card",
  "content-viewed",
  "hint-requested",
  "answer-selected",
  "code-run",
  "code-submitted",
  "open-review",
  "prepare-review-retest",
  "navigate",
]);

const drawerOpen = ref(false);
const activeResourceCategory = ref("all"); // which content type is active
const learnPanelRef = ref(null);
const coachPanelRef = ref(null);

const highContrast = ref(false);
const reduceMotion = ref(false);
const fontSize = ref(16);
const mobilePane = ref("learn");
const mobileTab = ref("learn");
const tutorCollapsed = ref(false);
const isWorkspaceBusy = computed(() => props.isBusy || props.isLoadingNode);

const dockActions = [
  { key: "learn", label: "内容" },
  { key: "coach", label: "导师" },
  { key: "path", label: "路径" },
  { key: "notes", label: "笔记" },
];

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

const FOCUS_CARD_CATEGORY = {
  concept_map: "concept",
  code_snippet: "code",
  interactive_exercise: "practice",
  video_summary: "video",
  diagnostic_quiz: "quiz",
};

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
      mobileTab.value = "coach";
      drawerOpen.value = false;
      return;
    }

    syncLearningView(props.learningView);
  },
  { immediate: true },
);

watch(
  () => props.learningView,
  (view) => {
    if (props.bootMode !== "probe") syncLearningView(view);
  },
  { immediate: true },
);

function syncLearningView(view) {
  if (view === "coach") {
    mobilePane.value = "coach";
    mobileTab.value = "coach";
    drawerOpen.value = false;
    void focusWorkspaceRegion("coach");
  } else if (view === "path") {
    mobilePane.value = "learn";
    mobileTab.value = "path";
    drawerOpen.value = true;
  } else if (view === "notes") {
    mobilePane.value = "learn";
    mobileTab.value = "notes";
    drawerOpen.value = false;
    void nextTick(showNotes);
  } else {
    mobilePane.value = "learn";
    mobileTab.value = "learn";
    drawerOpen.value = false;
    void focusWorkspaceRegion("learn");
  }
}

watch(
  [
    () => props.learningView,
    () => props.cards.length,
    () => props.isLoadingNode,
  ],
  ([view, cardCount, loading]) => {
    if (view === "notes" && cardCount > 0 && !loading) {
      void nextTick(showNotes);
    }
  },
  { flush: "post" },
);

// A review route can change its required card while the learner is already
// filtering the canvas. Keep the visible category aligned with that route so
// a fresh retest cannot remain hidden behind the prior practice card.
watch(
  () => props.focusCardType,
  (cardType) => {
    const category = FOCUS_CARD_CATEGORY[cardType];
    if (!category) {
      return;
    }
    activeResourceCategory.value = category;
    mobilePane.value = "learn";
    mobileTab.value = "learn";
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

function onSelectNode(nodeId) {
  emit("select-node", nodeId);
  drawerOpen.value = false;
}

function closeDrawer() {
  drawerOpen.value = false;
  if (mobileTab.value === "path") {
    mobileTab.value = "learn";
    emit("navigate", "learn");
  }
}

function onSwitchCourse(courseId) {
  emit("switch-course", courseId);
}

function handleBrowseCourses() {
  emit("browse-courses");
}

function handleCoachSend(message) {
  mobilePane.value = "coach";
  mobileTab.value = "coach";
  emit("navigate", "coach");
  emit("send-tutor", message);
}

async function handleNav(key) {
  emit("navigate", key);
  mobileTab.value = key;

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
    mobilePane.value = "learn";
    drawerOpen.value = true;
    return;
  }

  if (key === "notes") {
    mobilePane.value = "learn";
    drawerOpen.value = false;
    await nextTick();
    showNotes();
    return;
  }
}

function isDrawerAction(key) {
  return key === "path";
}

function isNavActive(key) {
  return mobileTab.value === key;
}

function navTargetId(key) {
  if (key === "learn") {
    return LEARN_PANEL_ID;
  }

  if (key === "coach") {
    return COACH_PANEL_ID;
  }

  if (key === "path") {
    return DRAWER_PANEL_ID;
  }

  return undefined;
}

function navExpandedState(key) {
  return isDrawerAction(key) ? String(drawerOpen.value) : undefined;
}

function toggleTutor() {
  tutorCollapsed.value = !tutorCollapsed.value;
}

function showNotes() {
  if (typeof learnPanelRef.value?.scrollToAnnotations === "function") {
    learnPanelRef.value.scrollToAnnotations();
  }
}

async function focusWorkspaceRegion(key) {
  if (typeof window === "undefined" || window.matchMedia("(min-width: 1280px)").matches) {
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
  return isNavActive(key) ? "is-active" : "";
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

function flushLearningAssets() {
  return coachPanelRef.value?.flushLearningAssets?.() ?? Promise.resolve();
}

defineExpose({ flushLearningAssets });
</script>

<style scoped>
.workspace-pane-layout {
  display: flex;
  flex-direction: column;
  background: var(--space-bg);
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
  padding: 0.5rem 0.65rem calc(env(safe-area-inset-bottom, 0px) + 0.5rem);
}

.mobile-dock__actions {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.35rem;
}

.mobile-dock__action {
  min-height: 2.75rem;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 0.74rem;
  font-weight: 650;
  line-height: 1;
  padding: 0.5rem 0.25rem;
  white-space: nowrap;
}

.mobile-dock__action.is-active {
  border-color: color-mix(in srgb, var(--color-primary) 25%, var(--border-subtle));
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
}

.mobile-dock__action:active {
  transform: translateY(1px);
}

@media (min-width: 1280px) {
  .workspace-pane-layout {
    display: grid;
    grid-template-columns: minmax(0, 5fr) minmax(0, 3fr);
    gap: 0;
    padding: 0;
  }

  .workspace-pane-layout.has-collapsed-tutor {
    grid-template-columns: minmax(0, 1fr);
  }

  .workspace-pane-layout__pane,
  .workspace-pane-layout__pane.is-active-mobile {
    display: flex;
    min-width: 0;
    min-height: 0;
  }

  .workspace-pane-layout__learning {
    border-right: 1px solid var(--border-subtle);
  }

  .workspace-pane-layout__tutor.is-collapsed-desktop {
    display: none;
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
