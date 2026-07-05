<template>
  <div
    class="workspace-shell relative z-10 flex h-screen overflow-hidden font-sans text-text-primary animate-fadeIn"
    :class="{
      'is-high-contrast': highContrast,
      'is-reduced-motion': reduceMotion,
    }"
    :aria-busy="isWorkspaceBusy ? 'true' : 'false'"
    :style="{ fontSize: `${fontSize}px` }"
    @wheel="forwardWorkspaceWheel"
  >
    <SidebarRail
      :active-panel="sidebarPanel"
      :drawer-open="drawerOpen"
      panel-id="workspace-sidebar-drawer"
      :path-count="pathNodes.length"
      @select="onSidebarSelect"
    />

    <div class="relative flex min-w-0 flex-1 flex-col">
      <header class="workspace-topbar relative z-20 px-4 py-3 sm:px-5 lg:px-6">
        <div class="workspace-topbar__row flex flex-wrap items-center gap-3 lg:flex-nowrap">
          <div class="workspace-topbar__brand flex min-w-0 flex-shrink-0 items-center gap-3 lg:hidden">
            <div class="workspace-topbar__badge flex h-11 w-11 items-center justify-center rounded-[16px] text-sm font-black text-text-primary">
              EA
            </div>
            <div class="workspace-topbar__copy hidden min-w-0 sm:block">
              <span class="block text-sm font-black leading-tight tracking-tight text-text-primary">
                EduAgent
              </span>
              <span class="block truncate text-[10px] font-medium tracking-[0.12em] text-text-muted">
                课程学习工作台
              </span>
            </div>
          </div>

          <nav
            class="topbar-pivot hidden flex-shrink-0 items-center gap-1 rounded-full p-1.5 xl:flex"
            aria-label="工作台主导航"
          >
            <button
              v-for="item in workspaceNav"
              :key="item.key"
              type="button"
              class="focus-ring rounded-full px-3.5 py-2 text-[11px] font-semibold tracking-[0.08em] transition-all duration-200"
              :class="navButtonClass(item.key)"
              :aria-controls="navTargetId(item.key)"
              :aria-expanded="navExpandedState(item.key)"
              :aria-haspopup="isDrawerAction(item.key) ? 'dialog' : undefined"
              :aria-pressed="String(isNavActive(item.key))"
              @click="handleNav(item.key)"
            >
              {{ item.label }}
            </button>
          </nav>

          <div class="topbar-status-shell hidden min-w-0 flex-1 justify-center overflow-hidden md:flex">
            <TopStatusBar :statuses="statuses" />
          </div>

          <div class="workspace-topbar__actions ml-auto flex flex-shrink-0 items-center gap-2 sm:gap-3">
            <div v-if="activeCourse || enrolledCourses.length" class="relative">
              <button
                ref="courseMenuTriggerRef"
                type="button"
                class="workspace-course-switch focus-ring flex min-w-0 items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-semibold text-text-secondary transition-all duration-200 w-auto"
                :aria-controls="'workspace-course-menu'"
                :aria-expanded="String(courseMenuOpen)"
                aria-haspopup="menu"
                @click="toggleCourseMenu"
                @keydown.down.prevent="openCourseMenu('first')"
                @keydown.up.prevent="openCourseMenu('last')"
              >
                <span class="text-base leading-none">{{ activeCourse?.icon || "📌" }}</span>
                <span class="max-w-[128px] truncate sm:max-w-[120px] xl:max-w-[140px]">{{ activeCourse?.title_cn || "课程" }}</span>
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
                  ref="courseMenuRef"
                  id="workspace-course-menu"
                  class="absolute right-0 top-full z-50 mt-2 w-64 rounded-2xl border border-subtle bg-space-panel p-2 shadow-2xl backdrop-blur-xl"
                  role="menu"
                  aria-label="已选课程"
                  tabindex="-1"
                  @click.stop
                  @keydown="onCourseMenuKeydown"
                >
                  <p class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.14em] text-text-muted">已选课程</p>
                  <button
                    v-for="course in enrolledCourses"
                    :key="course.course_id"
                    type="button"
                    data-course-menu-item="true"
                    role="menuitemradio"
                    :aria-checked="String(course.course_id === activeCourse?.course_id)"
                    class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-colors duration-150 hover:bg-card"
                    :class="course.course_id === activeCourse?.course_id ? 'bg-primary-soft/20 text-primary' : 'text-text-secondary'"
                    @click="onSwitchCourse(course.course_id)"
                  >
                    <span class="text-lg">{{ course.icon || "📌" }}</span>
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
                    data-course-menu-item="true"
                    role="menuitem"
                    class="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-sm text-text-muted transition-colors hover:bg-card hover:text-primary"
                    @click="handleBrowseCourses"
                  >
                    <span class="text-base">+</span>
                    浏览更多课程
                  </button>
                </div>
              </transition>
              <div
                v-if="courseMenuOpen"
                class="fixed inset-0 z-40"
                @click="closeCourseMenu({ restoreFocus: true })"
              />
            </div>

            <button
              type="button"
              class="workspace-utility-btn focus-ring hidden rounded-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted transition-all duration-200 sm:inline-flex"
              @click="$emit('go-home')"
            >
              首页
            </button>

            <span class="workspace-user-chip hidden text-xs font-medium text-text-secondary sm:inline">
              {{ user?.display_name || user?.user_id || "未登录" }}
            </span>

            <button
              type="button"
              class="workspace-utility-btn workspace-utility-btn--danger focus-ring hidden rounded-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted transition-all duration-200 sm:inline-flex"
              @click="$emit('logout')"
            >
              退出
            </button>
          </div>
        </div>

        <div class="workspace-mobile-meta mt-3 flex items-center justify-between gap-3 pt-3 sm:hidden">
          <span class="workspace-mobile-meta__user min-w-0 truncate text-xs font-medium text-text-secondary">
            {{ user?.display_name || user?.user_id || "未登录" }}
          </span>

          <div class="flex items-center gap-2">
            <button
              type="button"
              class="workspace-utility-btn focus-ring rounded-full px-3 py-1.5 text-[11px] font-semibold text-text-muted transition-all duration-200"
              @click="$emit('go-home')"
            >
              首页
            </button>
            <button
              type="button"
              class="workspace-utility-btn workspace-utility-btn--danger focus-ring rounded-full px-3 py-1.5 text-[11px] font-semibold text-text-muted transition-all duration-200"
              @click="$emit('logout')"
            >
              退出
            </button>
          </div>
        </div>

        <div class="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-[var(--border-strong)] to-transparent" />
      </header>

      <div class="relative flex min-h-0 flex-1 flex-col">
        <section class="border-b border-subtle px-4 py-4 backdrop-blur-sm sm:px-5 lg:px-6">
          <div class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(360px,440px)] xl:items-start">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">学习驾驶舱</p>
                <span class="workspace-shell-chip workspace-shell-chip--accent px-3 py-1 text-[11px] font-semibold">
                  {{ studyStage }}
                </span>
              </div>

              <div class="mt-3 flex flex-wrap items-end gap-x-4 gap-y-2">
                <h1 class="truncate text-[24px] font-black tracking-tight text-text-primary sm:text-[30px] lg:text-[34px]">
                  {{ activeCourse?.title_cn || "课程工作台" }}
                </h1>
                <span class="workspace-shell-chip px-3 py-1 text-[11px] font-semibold text-text-secondary">
                  {{ currentNodeCaption }}
                </span>
              </div>

              <p class="mt-3 max-w-3xl text-xs leading-5 text-text-muted sm:text-sm sm:leading-6">
                当前节点：
                <span class="font-semibold text-text-secondary">{{ nodeTitle || "等待生成学习路径" }}</span>
                <span v-if="nextNode" class="ml-1">· 下一建议节点：{{ nextNode.title }}</span>
              </p>

              <div class="workspace-shell-card mt-4 rounded-2xl px-4 py-4 sm:px-5 sm:py-5">
                <div class="flex flex-wrap items-center gap-2">
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">当前建议</p>
                  <span class="workspace-shell-chip px-3 py-1 text-[11px] font-semibold text-text-secondary">
                    {{ learningSequenceTitle }}
                  </span>
                </div>
                <div class="mt-3 flex flex-wrap items-start justify-between gap-3">
                  <p class="max-w-[36rem] text-base font-semibold leading-7 text-text-primary sm:text-[17px]">{{ focusTitle }}</p>
                  <div class="workspace-shell-card-soft min-w-[172px] rounded-[18px] px-4 py-3">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">当前推进</p>
                    <p class="mt-2 text-2xl font-black text-text-primary">{{ currentMastery }}%</p>
                    <p class="mt-1 text-[11px] leading-5 text-text-muted">
                      {{ nextNode ? `下一节点：${nextNode.title}` : "主线路径已接近完成" }}
                    </p>
                  </div>
                </div>
                <div class="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
                  <div class="workspace-shell-card-soft rounded-[18px] px-4 py-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">学习提要</p>
                    <p class="mt-2 text-sm leading-7 text-text-secondary">{{ focusDetail }}</p>
                  </div>
                  <div class="workspace-shell-card-soft rounded-[18px] px-4 py-4">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">推荐节奏</p>
                    <p class="mt-2 text-sm leading-7 text-text-secondary">{{ learningSequenceDetail }}</p>
                  </div>
                </div>
              </div>

              <div
                v-if="infoMessage"
                class="workspace-shell-card info-message mt-3 rounded-2xl px-3 py-2 text-xs leading-5 text-primary sm:mt-4 sm:px-4 sm:py-3"
              >
                {{ infoMessage }}
              </div>
            </div>

            <div class="hidden gap-3 md:grid md:grid-cols-2 xl:grid-cols-1 xl:self-start">
              <div
                v-for="metric in metrics"
                :key="metric.label"
                class="workspace-shell-card metric-tile rounded-2xl px-4 py-3"
              >
                <div class="flex items-center justify-between gap-3">
                  <p class="text-[10px] font-bold uppercase tracking-[0.12em] text-text-muted">{{ metric.label }}</p>
                  <p class="text-[24px] font-black tracking-tight text-text-primary">{{ metric.value }}</p>
                </div>
                <p class="mt-1 text-[11px] leading-5 text-text-muted">{{ metric.detail }}</p>
              </div>
            </div>
          </div>

        </section>

        <section class="border-b border-subtle px-4 py-3 sm:px-5 xl:hidden">
          <div class="aurora-scroll flex items-center gap-2 overflow-x-auto pb-1">
            <div
              v-for="status in compactStatuses"
              :key="`mobile-${status.key}`"
              class="workspace-shell-chip shrink-0 px-3 py-2"
              :class="status.panelClass"
            >
              <div class="flex items-center gap-2">
                <span class="text-[11px] font-semibold text-text-primary">{{ status.label }}</span>
                <span class="text-[10px] text-text-muted">{{ status.phase }}</span>
                <span class="text-[10px] font-mono text-text-muted">{{ status.progress }}%</span>
              </div>
            </div>
          </div>
        </section>

        <div
          class="safe-bottom min-h-0 overflow-hidden xl:col-start-1 xl:row-start-2"
          :class="effectiveMobilePane === 'learn' ? 'block flex-1' : 'hidden xl:block xl:flex-1'"
        >
            <main
              id="workspace-learn-panel"
              ref="learnPanelRef"
              class="h-full min-w-0"
              tabindex="-1"
              aria-label="学习资源画布"
            >
              <ResourceCanvas
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
            </main>
        </div>

        <aside
              id="workspace-coach-panel"
              ref="coachPanelRef"
              class="safe-bottom min-w-0 border-t border-subtle bg-space-surface/50 backdrop-blur-sm xl:hidden"
              :class="effectiveMobilePane === 'coach' ? 'flex flex-1 flex-col' : 'hidden'"
              tabindex="-1"
              aria-label="辅导通道（移动端）"
            >
              <div class="min-h-0 overflow-y-auto border-b border-subtle/70 px-4 py-4 sm:px-5">
                <AgentFeedbackPanel
                  :feedback-items="agentFeedback"
                  :last-diagnostic="lastDiagnostic"
                  :current-node-title="nodeTitle"
                />
              </div>
              <div class="min-h-0 flex-1">
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
              </div>
        </aside>

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

      <!-- 悬浮学习托盘 (桌面端) -->
      <FloatingChatTray
        :messages="messages"
        :boot-mode="bootMode"
        :probe="probe"
        :probe-collected="probeCollected"
        :probe-total="probeTotal"
        :is-submitting-probe="isSubmittingProbe"
        :busy="isBusy"
        :node-title="nodeTitle"
        :suggestions="coachPrompts"
        class="hidden xl:block"
        @send="handleCoachSend"
        @submit-probe="(values) => $emit('submit-probe', values)"
      />

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
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import AgentFeedbackPanel from "./AgentFeedbackPanel.vue";
import ChatArea from "./ChatArea.vue";
import FloatingChatTray from "./FloatingChatTray.vue";
import IconCheck from "./icons/IconCheck.vue";
import ResourceCanvas from "./ResourceCanvas.vue";
import SidebarDrawer from "./SidebarDrawer.vue";
import SidebarRail from "./SidebarRail.vue";
import TopStatusBar from "./TopStatusBar.vue";

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
const activeWorkspaceView = ref("learn");       // "learn" | "home"
const courseMenuOpen = ref(false);
const courseMenuTriggerRef = ref(null);
const courseMenuRef = ref(null);
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
    return "保持当前节点，等待学习资源装配完成";
  }

  if (!props.cards.length) {
    return "先装配当前节点的学习资源";
  }

  if (currentMastery.value < 65) {
    return "优先学透当前节点，再向后推进";
  }

  return nextNode.value ? `准备推进到下一个薄弱节点：${nextNode.value.title}` : "当前主路径已接近完成";
});

const focusDetail = computed(() => {
  if (props.bootMode === "probe") {
    return "诊断结果会决定学习起点、资源密度和后续节点顺序，先完成它比直接开始更有效率。";
  }

  if (props.isLoadingNode) {
    return "资源生成阶段不建议频繁切换节点，等待概念、代码、练习和诊断内容全部到位后再继续。";
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
    ? "这一路径更接近真实学习平台的内容编排逻辑，先建立认知骨架，再进入操作与验证。"
    : "当前节点资源生成完成后，矩阵会自动排列为适合连续学习的顺序。"
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
      closeCourseMenu();
    }
  },
  { immediate: true },
);

watch(courseMenuOpen, async (isOpen) => {
  if (!isOpen) {
    return;
  }

  await nextTick();
  focusCourseMenuItem("selected");
});

watch(drawerOpen, (isOpen) => {
  if (isOpen) {
    closeCourseMenu();
  }
});

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

onBeforeUnmount(() => {
  courseMenuOpen.value = false;
});

async function openCourseMenu(target = "selected") {
  courseMenuOpen.value = true;
  await nextTick();
  focusCourseMenuItem(target);
}

function toggleCourseMenu() {
  if (courseMenuOpen.value) {
    closeCourseMenu({ restoreFocus: true });
    return;
  }

  openCourseMenu();
}

function closeCourseMenu({ restoreFocus = false } = {}) {
  if (!courseMenuOpen.value && !restoreFocus) {
    return;
  }

  courseMenuOpen.value = false;
  if (!restoreFocus) {
    return;
  }

  nextTick(() => {
    if (courseMenuTriggerRef.value instanceof HTMLElement) {
      courseMenuTriggerRef.value.focus({ preventScroll: true });
    }
  });
}

function getCourseMenuItems() {
  if (!(courseMenuRef.value instanceof HTMLElement)) {
    return [];
  }

  return Array.from(courseMenuRef.value.querySelectorAll('[data-course-menu-item="true"]')).filter((element) => (
    element instanceof HTMLElement
  ));
}

function focusCourseMenuItem(target = "selected") {
  const items = getCourseMenuItems();
  if (!items.length) {
    return;
  }

  let index = 0;
  if (target === "last") {
    index = items.length - 1;
  } else if (target === "selected") {
    const selectedIndex = items.findIndex((item) => item.getAttribute("aria-checked") === "true");
    index = selectedIndex >= 0 ? selectedIndex : 0;
  }

  items[index]?.focus();
}

function moveCourseMenuFocus(step) {
  const items = getCourseMenuItems();
  if (!items.length) {
    return;
  }

  const currentIndex = items.findIndex((item) => item === document.activeElement);
  const safeIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = (safeIndex + step + items.length) % items.length;
  items[nextIndex]?.focus();
}

function onCourseMenuKeydown(event) {
  if (!courseMenuOpen.value) {
    return;
  }

  if (event.key === "ArrowDown") {
    event.preventDefault();
    moveCourseMenuFocus(1);
    return;
  }

  if (event.key === "ArrowUp") {
    event.preventDefault();
    moveCourseMenuFocus(-1);
    return;
  }

  if (event.key === "Home") {
    event.preventDefault();
    focusCourseMenuItem("first");
    return;
  }

  if (event.key === "End") {
    event.preventDefault();
    focusCourseMenuItem("last");
    return;
  }

  if (event.key === "Escape") {
    event.preventDefault();
    closeCourseMenu({ restoreFocus: true });
    return;
  }

  if (event.key === "Tab") {
    window.setTimeout(() => closeCourseMenu(), 0);
  }
}

function onSidebarSelect(panelKey) {
  closeCourseMenu();
  // Content category keys → update filter, close drawer
  const CONTENT_KEYS = new Set(["concept", "code", "practice", "video", "quiz", "all"]);
  if (CONTENT_KEYS.has(panelKey)) {
    activeResourceCategory.value = panelKey;
    sidebarPanel.value = panelKey;
    drawerOpen.value = false;
    // Switch to learn view when selecting a content category
    if (activeWorkspaceView.value !== "learn") {
      activeWorkspaceView.value = "learn";
    }
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
  closeCourseMenu();
  sidebarPanel.value = panelKey;
  drawerOpen.value = true;
}

function onDrawerPanelSwitch(panelKey) {
  openPanel(panelKey);
}

function onSelectNode(nodeId) {
  closeCourseMenu();
  emit("select-node", nodeId);
  drawerOpen.value = false;
  mobilePane.value = "learn";
}

function onSwitchCourse(courseId) {
  closeCourseMenu({ restoreFocus: true });
  emit("switch-course", courseId);
}

function handleBrowseCourses() {
  closeCourseMenu({ restoreFocus: true });
  emit("go-home");
}

function handleCoachSend(message) {
  closeCourseMenu();
  mobilePane.value = "coach";
  emit("send-tutor", message);
}

async function handleNav(key) {
  closeCourseMenu();
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
  if (target instanceof HTMLElement) {
    target.focus({ preventScroll: true });
  }
}

function navButtonClass(key) {
  if (isNavActive(key)) {
    return "bg-primary-soft text-primary";
  }

  return "text-text-muted hover:bg-card-hover hover:text-text-secondary";
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

  const activePanel = effectiveMobilePane.value === "coach" ? coachPanelRef.value : learnPanelRef.value;
  if (!(activePanel instanceof HTMLElement)) {
    return;
  }

  const scrollCandidate = activePanel.querySelector("[data-chat-scroll='true'], .aurora-scroll");
  if (!(scrollCandidate instanceof HTMLElement)) {
    return;
  }

  if (scrollCandidate.contains(target)) {
    return;
  }

  scrollCandidate.scrollTop += event.deltaY;
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

.workspace-topbar {
  position: relative;
}

.workspace-topbar::before {
  content: "";
  position: absolute;
  inset: 0.5rem 1rem 0;
  border: 1px solid var(--border-subtle);
  border-radius: 1.15rem;
  background: var(--space-panel);
  box-shadow: var(--workspace-shadow-soft);
  pointer-events: none;
}

.workspace-topbar__row {
  position: relative;
  z-index: 1;
  min-height: 4.5rem;
  padding-inline: 0.65rem;
}

.workspace-topbar__brand {
  padding-right: 0.45rem;
}

.workspace-topbar__badge {
  border: 1px solid color-mix(in srgb, var(--color-primary) 24%, var(--border-subtle));
  background: var(--color-primary-soft);
  box-shadow: none;
  color: var(--color-primary-dark);
}

.workspace-topbar__copy {
  max-width: 10rem;
}

.topbar-pivot {
  border: 1px solid var(--border-subtle);
  background: var(--space-elevated);
  box-shadow: none;
}

.topbar-status-shell {
  position: relative;
  min-height: 3rem;
  border-inline: 1px solid color-mix(in srgb, var(--border-subtle) 92%, transparent);
  padding-inline: 1rem;
}

.workspace-topbar__actions {
  position: relative;
  z-index: 1;
}

.workspace-course-switch {
  border: 1px solid var(--border-subtle);
  background: var(--space-panel);
  box-shadow: none;
}

.workspace-course-switch:hover {
  border-color: color-mix(in srgb, var(--color-primary) 26%, var(--border-strong));
  color: var(--color-primary-dark);
  transform: translateY(-1px);
}

.workspace-utility-btn {
  border: 1px solid var(--border-subtle);
  background: var(--space-panel);
  box-shadow: none;
}

.workspace-utility-btn:hover {
  border-color: color-mix(in srgb, var(--color-primary) 24%, var(--border-strong));
  background: var(--space-elevated);
  color: var(--color-primary-dark);
}

.workspace-utility-btn--danger:hover {
  border-color: color-mix(in srgb, var(--color-error) 32%, var(--border-strong));
  color: var(--color-error);
}

.workspace-user-chip {
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--space-elevated);
  padding: 0.55rem 0.9rem;
  box-shadow: none;
}

.workspace-mobile-meta {
  position: relative;
  z-index: 1;
  border-top: 1px solid color-mix(in srgb, var(--border-subtle) 92%, transparent);
}

.workspace-mobile-meta__user {
  border-radius: 999px;
  background: var(--space-elevated);
  padding: 0.45rem 0.8rem;
}

@media (max-width: 639px) {
  .workspace-topbar::before {
    inset-inline: 0.6rem;
    border-radius: 1rem;
  }

  .workspace-topbar__row {
    padding-inline: 0.25rem;
  }
}

@media (min-width: 1024px) {
  .workspace-topbar__row {
    gap: 1rem;
  }
}

@media (min-width: 1280px) {
  .workspace-topbar__row {
    justify-content: space-between;
  }
}

.mobile-dock {
  z-index: 40;
  background: var(--space-panel);
  box-shadow: 0 -10px 24px rgba(15, 23, 42, 0.08);
  padding-bottom: calc(env(safe-area-inset-bottom, 0px) + 0.75rem);
}

.info-message {
  position: relative;
  z-index: 1;
}

.metric-tile {
  min-height: 5.75rem;
}

@media (min-width: 1280px) {
  .mobile-dock {
    padding-bottom: calc(env(safe-area-inset-bottom, 0px) + 0.75rem);
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
