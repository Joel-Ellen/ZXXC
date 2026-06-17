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

        <!-- 用户信息 + 操作（右侧） -->
        <div class="flex flex-shrink-0 items-center gap-3">
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
});

// ── Emits ──
const emit = defineEmits([
  "select-node",
  "submit-quiz",
  "send-tutor",
  "submit-probe",
  "logout",
  "go-home",
]);

// ── Sidebar 状态 ──
const drawerOpen = ref(false);
const sidebarPanel = ref("tree"); // "tree" | "radar" | "settings"

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
</script>
