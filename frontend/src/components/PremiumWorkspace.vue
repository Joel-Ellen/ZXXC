<template>
  <div
    class="relative z-10 flex h-screen overflow-hidden font-sans text-text-primary animate-fadeIn"
    :style="{ fontSize: `${fontSize}px` }"
  >
    <!-- ═══════════════════════════════════════════════════════════════ -->
    <!-- 侧边图标栏                                                      -->
    <!-- ═══════════════════════════════════════════════════════════════ -->
    <SidebarRail
      :active-panel="sidebarPanel"
      :drawer-open="drawerOpen"
      :path-count="pathNodes.length"
      @select="onSidebarSelect"
    />

    <!-- ═══════════════════════════════════════════════════════════════ -->
    <!-- 主体区域                                                        -->
    <!-- ═══════════════════════════════════════════════════════════════ -->
    <div class="relative flex min-w-0 flex-1 flex-col">
      <!-- ── 顶部栏：轻量玻璃胶囊 ── -->
      <header
        class="glass-panel relative z-20 flex items-center gap-4 px-6 py-3"
      >
        <!-- Logo -->
        <div class="flex flex-shrink-0 items-center gap-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-primary to-secondary text-sm font-black text-primary-text shadow-glow">
            EA
          </div>
          <div class="hidden sm:block">
            <span class="block text-sm font-black leading-tight tracking-tight text-text-primary">
              EduAgent
            </span>
            <span class="block text-[10px] font-medium uppercase tracking-[0.12em] text-text-muted">
              多智能体学习工作台
            </span>
          </div>
        </div>

        <!-- 智能体状态胶囊（居中） -->
        <div class="flex flex-1 justify-center overflow-hidden">
          <TopStatusBar :statuses="statuses" />
        </div>

        <!-- 课程切换 + 用户操作（右侧） -->
        <div class="flex flex-shrink-0 items-center gap-3">
          <!-- 课程切换器 -->
          <div class="relative" v-if="activeCourse || enrolledCourses.length">
            <button
              type="button"
              class="focus-ring flex items-center gap-2 rounded-full border border-subtle bg-card px-3.5 py-1.5 text-[11px] font-semibold text-text-secondary transition-all duration-200 hover:border-primary/30 hover:text-primary hover:bg-card-hover"
              @click="courseMenuOpen = !courseMenuOpen"
            >
              <span class="text-base leading-none">{{ activeCourse?.icon || '📚' }}</span>
              <span class="max-w-[120px] truncate hidden sm:inline">{{ activeCourse?.title_cn || '课程' }}</span>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" class="transition-transform duration-200" :class="courseMenuOpen ? 'rotate-180' : ''">
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>
            <!-- Dropdown -->
            <transition name="fade">
              <div v-if="courseMenuOpen" class="absolute right-0 top-full mt-2 z-50 w-60 rounded-2xl border border-subtle bg-space-panel p-2 shadow-2xl backdrop-blur-xl" @click.stop>
                <p class="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.14em] text-text-muted">已选课程</p>
                <button
                  v-for="c in enrolledCourses"
                  :key="c.course_id"
                  type="button"
                  class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-colors duration-150 hover:bg-card"
                  :class="c.course_id === activeCourse?.course_id ? 'bg-primary-soft/20 text-primary' : 'text-text-secondary'"
                  @click="onSwitchCourse(c.course_id)"
                >
                  <span class="text-lg">{{ c.icon || '📚' }}</span>
                  <div class="flex-1 min-w-0">
                    <span class="block truncate text-sm font-medium">{{ c.title_cn }}</span>
                    <span class="block text-[10px] text-text-muted">{{ c.progress ? Math.round(c.progress * 100) : 0 }}%</span>
                  </div>
                  <IconCheck v-if="c.course_id === activeCourse?.course_id" :size="14" class="text-primary shrink-0" />
                </button>
                <div class="my-1 h-px bg-subtle" />
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
            <!-- Backdrop -->
            <div v-if="courseMenuOpen" class="fixed inset-0 z-40" @click="courseMenuOpen = false" />
          </div>

          <button
            type="button"
            class="focus-ring rounded-full border border-subtle bg-card px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted transition-all duration-200 hover:border-primary/30 hover:text-primary hover:bg-primary-soft"
            @click="$emit('go-home')"
          >
            首页
          </button>
          <span class="hidden text-xs font-medium text-text-secondary sm:inline">
            {{ user?.display_name || user?.user_id || '未登录' }}
          </span>
          <button
            type="button"
            class="focus-ring rounded-full border border-subtle bg-card px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted transition-all duration-200 hover:border-error/30 hover:text-error hover:bg-error-soft"
            @click="$emit('logout')"
          >
            退出
          </button>
        </div>

        <!-- 渐变阴影遮罩（下方） -->
        <div class="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-[var(--border-strong)] to-transparent" />
      </header>

      <!-- ── 三栏内容区 ── -->
      <div class="relative flex min-h-0 flex-1">
        <!-- ChatArea：左侧辅导通道（~380px） -->
        <div class="w-[380px] flex-shrink-0 border-r border-subtle bg-space-surface/50 backdrop-blur-sm">
          <ChatArea
            :messages="messages"
            :boot-mode="bootMode"
            :probe="probe"
            :probe-collected="probeCollected"
            :probe-total="probeTotal"
            :is-submitting-probe="isSubmittingProbe"
            :busy="isBusy"
            @send="(msg) => $emit('send-tutor', msg)"
            @submit-probe="(values) => $emit('submit-probe', values)"
          />
        </div>

        <!-- ResourceCanvas：右侧多模态画布（flex-1） -->
        <div class="min-w-0 flex-1 bg-space-bg/40">
          <ResourceCanvas
            :cards="cards"
            :current-node="currentNode"
            :node-title="nodeTitle"
            :path-nodes="pathNodes"
            :loading="isLoadingNode"
            :get-card-label="getCardLabel"
            :get-agent-label="getAgentLabel"
            :build-quiz="parseQuiz"
            @submit-quiz="(score) => $emit('submit-quiz', score)"
            @select-node="(id) => onSelectNode(id)"
          />
        </div>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════ -->
      <!-- SidebarDrawer：浮动覆盖层                                       -->
      <!-- ═══════════════════════════════════════════════════════════════ -->
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
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import ChatArea from "./ChatArea.vue";
import IconCheck from "./icons/IconCheck.vue";
import ResourceCanvas from "./ResourceCanvas.vue";
import SidebarDrawer from "./SidebarDrawer.vue";
import SidebarRail from "./SidebarRail.vue";
import TopStatusBar from "./TopStatusBar.vue";

// ── Props（全部来自 useEduAgent） ──
defineProps({
  bootMode: { type: String, default: "loading" },
  user: { type: Object, default: null },
  currentNode: { type: String, default: "" },
  cards: { type: Array, default: () => [] },
  pathNodes: { type: Array, default: () => [] },
  nodeTitle: { type: String, default: "" },
  messages: { type: Array, default: () => [] },
  capabilityRadar: { type: Array, default: () => [0.5, 0.5, 0.5, 0.5, 0.5] },
  statuses: { type: Array, default: () => [] },
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

// ── Emits ──
const emit = defineEmits([
  "select-node",
  "submit-quiz",
  "send-tutor",
  "submit-probe",
  "logout",
  "go-home",
  "switch-course",
]);

// ── Sidebar 状态 ──
const drawerOpen = ref(false);
const sidebarPanel = ref("tree"); // "tree" | "radar" | "settings"
const courseMenuOpen = ref(false);

// ── 无障碍 / 视觉偏好 ──
const highContrast = ref(false);
const reduceMotion = ref(false);
const fontSize = ref(16);

// ── 方法 ──
function onSidebarSelect(panelKey) {
  if (sidebarPanel.value === panelKey && drawerOpen.value) {
    drawerOpen.value = false;
  } else {
    sidebarPanel.value = panelKey;
    drawerOpen.value = true;
  }
}

function onSelectNode(nodeId) {
  emit("select-node", nodeId);
  drawerOpen.value = false;
}

function onSwitchCourse(courseId) {
  courseMenuOpen.value = false;
  emit("switch-course", courseId);
}
</script>
