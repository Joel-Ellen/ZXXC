<template>
  <transition name="drawer-backdrop">
<<<<<<< HEAD
    <div
      v-if="open"
      class="sidebar-drawer-layer fixed inset-0"
      @click.self="$emit('close')"
    >
      <div
        class="absolute inset-0 bg-black/42 backdrop-blur-[3px] transition-opacity lg:bg-[color:rgba(8,14,28,0.16)] lg:backdrop-blur-[1px]"
        aria-hidden="true"
=======
    <div v-if="open" class="fixed inset-0 z-40 lg:z-30">
      <button
        type="button"
        class="absolute inset-0 w-full bg-black/42 backdrop-blur-[3px] lg:bg-[color:rgba(8,14,28,0.16)] lg:backdrop-blur-[1px]"
        aria-label="关闭学习路径"
>>>>>>> origin/main
        @click="$emit('close')"
      />

      <transition name="drawer-panel">
        <aside
          v-if="open"
          :id="panelId"
<<<<<<< HEAD
          class="drawer-surface absolute bottom-4 left-4 right-4 top-24 z-10 flex overflow-hidden rounded-[20px] border border-[color:rgba(255,255,255,0.55)] shadow-[0_28px_80px_rgba(15,23,42,0.24)] lg:bottom-4 lg:left-auto lg:right-4 lg:top-4 lg:w-[428px]"
=======
          ref="drawerPanel"
          class="drawer-surface absolute bottom-4 left-4 right-4 top-24 z-10 flex overflow-hidden rounded-[24px] border border-[color:rgba(255,255,255,0.55)] bg-space-panel shadow-[0_28px_80px_rgba(15,23,42,0.24)] lg:inset-y-4 lg:left-[76px] lg:right-auto lg:top-4 lg:w-[408px] lg:rounded-l-none lg:border-l-0"
>>>>>>> origin/main
          role="dialog"
          aria-modal="true"
          aria-labelledby="learning-path-title"
          tabindex="-1"
        >
          <div class="drawer-surface__glow pointer-events-none absolute inset-0" />

          <div class="relative flex min-h-0 w-full flex-col">
            <header class="relative flex items-start gap-4 border-b border-subtle px-6 pb-5 pt-6">
              <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-[16px] bg-primary-soft text-primary shadow-card">
                <IconTree :size="22" />
              </div>
<<<<<<< HEAD

              <div class="min-w-0 flex-1">
                <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">{{ panelEyebrow }}</p>
                <h2 class="gradient-text mt-1.5 text-[28px] font-black tracking-tight">{{ panelTitle }}</h2>
=======
              <div class="min-w-0 flex-1 pr-8">
                <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">课程路径</p>
                <h2 id="learning-path-title" class="mt-1.5 text-[28px] font-black tracking-tight text-text-primary">学习节点</h2>
>>>>>>> origin/main
                <p class="mt-2 max-w-[34ch] text-sm font-light leading-7 text-text-muted">
                  查看真实掌握状态，并直接跳转到下一步值得投入的节点。
                </p>
              </div>
<<<<<<< HEAD
            </div>

            <div v-if="activePanel !== 'settings'" class="px-6 pb-4 pt-4">
              <nav
                class="grid grid-cols-3 gap-2 rounded-[20px] border border-subtle bg-card/92 p-1.5 shadow-card"
                aria-label="工作台抽屉视图切换"
                role="tablist"
=======
              <button
                ref="closeButton"
                type="button"
                class="focus-ring absolute right-4 top-4 rounded-full border border-subtle/70 bg-card/82 p-2 text-text-muted shadow-sm transition hover:bg-card-hover hover:text-text-primary"
                aria-label="关闭学习路径"
                @click="$emit('close')"
>>>>>>> origin/main
              >
                <span aria-hidden="true">×</span>
              </button>
            </header>

<<<<<<< HEAD
            <div class="aurora-scroll flex-1 overflow-y-auto px-5 pb-6">
              <transition name="drawer-content" mode="out-in">
                <div :key="activePanel">
              <template v-if="activePanel === 'tree'">
                <section
                  :id="panelRegionId('tree')"
                  class="mb-5 rounded-[20px] border border-subtle bg-card p-5 shadow-card"
                  role="tabpanel"
                  :aria-labelledby="panelTabId('tree')"
                >
                  <div class="grid gap-3 sm:grid-cols-3">
                    <div
                      v-for="stat in pathStats"
                      :key="stat.label"
                      class="rounded-[16px] border border-subtle bg-space-surface px-4 py-3"
                    >
                      <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">{{ stat.label }}</p>
                      <p class="mt-2 text-lg font-black text-text-primary">{{ stat.value }}</p>
                      <p class="mt-1 text-[11px] leading-5 text-text-muted">{{ stat.detail }}</p>
                    </div>
                  </div>
                </section>

                <KnowledgeTree
                  :nodes="nodes"
                  :current-node="currentNode"
                  @select="$emit('select-node', $event)"
                />
              </template>

              <template v-else-if="activePanel === 'radar'">
                <section
                  v-if="lastDiagnostic"
                  class="mb-5 rounded-[20px] border border-subtle bg-card p-5 shadow-card"
                >
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">最近诊断</p>
                  <div class="mt-3 flex items-end justify-between gap-4">
                    <div>
                      <p class="text-sm font-semibold text-text-primary">{{ currentNodeTitle || "当前节点" }}</p>
                      <p class="mt-1 text-xs leading-5 text-text-muted">
                        {{ lastDiagnostic.advancedToNextNode ? "已达到推进条件" : "继续积累有效学习证据" }}
                      </p>
                    </div>
                    <strong class="font-mono text-lg text-primary">
                      {{ Math.round((lastDiagnostic.masteryBefore ?? 0) * 100) }}% → {{ Math.round((lastDiagnostic.masteryAfter ?? 0) * 100) }}%
                    </strong>
                  </div>
                </section>

                <section
                  :id="panelRegionId('radar')"
                  class="mb-5 rounded-[20px] border border-subtle bg-card p-5 shadow-card"
                  role="tabpanel"
                  :aria-labelledby="panelTabId('radar')"
                >
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">能力说明</p>
                  <p class="mt-2 text-sm leading-7 text-text-muted">
                    雷达图用于帮助学习者判断自己的薄弱象限，不是单纯展示分数。建议结合当前节点和最近诊断一起阅读。
                  </p>
                </section>
                <RadarCanvas
                  :values="radarValues"
                  :high-contrast="highContrast"
                />

                <!-- 能力维度指标卡片 -->
                <section
                  class="mt-5 rounded-[20px] border border-subtle bg-card p-5 shadow-card"
                >
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">维度详情</p>
                  <div class="mt-3 space-y-2">
                    <div
                      v-for="(dim, idx) in radarDimensions"
                      :key="dim.key"
                      class="flex items-center justify-between rounded-xl border border-subtle px-4 py-2.5"
                    >
                      <span class="text-xs font-semibold text-text-primary">{{ dim.label }}</span>
                      <div class="flex items-center gap-2">
                        <div class="h-2 w-20 overflow-hidden rounded-full bg-space-surface">
                          <div
                            class="h-full rounded-full transition-all duration-500"
                            :class="radarBarClass(radarValues[idx] ?? 0.5)"
                            :style="{ width: `${Math.round((radarValues[idx] ?? 0.5) * 100)}%` }"
                          />
                        </div>
                        <span
                          class="min-w-[2.5rem] text-right text-xs font-mono font-semibold"
                          :class="radarTextClass(radarValues[idx] ?? 0.5)"
                        >
                          {{ Math.round((radarValues[idx] ?? 0.5) * 100) }}%
                        </span>
                      </div>
                    </div>
                  </div>
                </section>
              </template>

              <template v-else-if="activePanel === 'feedback'">
                <div
                  :id="panelRegionId('feedback')"
                  role="tabpanel"
                  :aria-labelledby="panelTabId('feedback')"
                >
                  <AgentFeedbackPanel
                    :feedback-items="feedbackItems"
                    :last-diagnostic="lastDiagnostic"
                    :current-node-title="currentNodeTitle"
                  />
                </div>
              </template>

              <div
                v-else
                :id="panelRegionId('settings')"
                class="space-y-5"
                role="tabpanel"
                :aria-labelledby="panelTabId('settings')"
              >
                <section class="rounded-[20px] border border-subtle bg-card p-5 shadow-card">
                  <h3 class="text-sm font-bold tracking-wide text-text-secondary">配色主题</h3>
                  <p class="mt-2 text-sm font-light leading-7 text-text-muted">
                    在深色与浅色主题之间切换，保持当前美术语言不变，只调整阅读环境与明度层次。
                  </p>
                  <div class="mt-5 flex gap-2 rounded-xl border border-subtle bg-card p-1">
                    <button
                      type="button"
                      class="focus-ring flex flex-1 items-center justify-center gap-2 rounded-lg py-2 text-xs font-semibold tracking-wide transition-all duration-200"
                      :class="theme === 'dark'
                        ? 'bg-card-hover text-text-primary shadow-lg shadow-black/20'
                        : 'text-text-muted hover:text-text-secondary'"
                      @click="setTheme('dark')"
                    >
                      <span class="h-3 w-3 rounded-full border border-white/20 bg-[#05060A]" />
                      深色
                    </button>
                    <button
                      type="button"
                      class="focus-ring flex flex-1 items-center justify-center gap-2 rounded-lg py-2 text-xs font-semibold tracking-wide transition-all duration-200"
                      :class="theme === 'light'
                        ? 'bg-card-hover text-text-primary shadow-lg shadow-black/20'
                        : 'text-text-muted hover:text-text-secondary'"
                      @click="setTheme('light')"
                    >
                      <span class="h-3 w-3 rounded-full border border-black/10 bg-[#FAFAF8]" />
                      浅色
                    </button>
                  </div>
                </section>

                <section class="rounded-[20px] border border-subtle bg-card p-5 shadow-card">
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <h3 class="text-sm font-bold tracking-wide text-text-secondary">高对比度</h3>
                      <p class="mt-2 text-sm font-light leading-7 text-text-muted">
                        提升主题对比度，适合长时间阅读或节点较多时的快速扫读。
                      </p>
                    </div>
                    <button
                      type="button"
                      class="focus-ring rounded-full border px-4 py-2 text-xs font-semibold tracking-wide transition-all duration-200"
                      :class="highContrast
                        ? 'border-primary/35 bg-primary-soft text-primary'
                        : 'border-subtle bg-card text-text-secondary hover:border-primary/40 hover:text-primary hover:bg-card-hover'"
                      @click="$emit('toggle-contrast')"
                    >
                      {{ highContrast ? "已启用" : "启用" }}
                    </button>
                  </div>
                </section>

                <section class="rounded-[20px] border border-subtle bg-card p-5 shadow-card">
                  <h3 class="text-sm font-bold tracking-wide text-text-secondary">基础字号</h3>
                  <p class="mt-2 text-sm font-light leading-7 text-text-muted">
                    在工作台 14 到 20 像素之间调节文字基准，让阅读密度更贴合使用环境。
                  </p>
                  <input
                    id="workspace-font-size"
                    class="mt-5 h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-[var(--border-strong)] accent-primary"
                    type="range"
                    min="14"
                    max="20"
                    step="1"
                    :value="fontSize"
                    aria-label="工作台基础字号"
                    :aria-valuetext="`${fontSize} 像素`"
                    @input="$emit('set-font-size', Number($event.target.value))"
                  />
                  <div class="mt-2 flex items-center justify-between text-xs text-text-muted">
                    <span>较小</span>
                    <output for="workspace-font-size" class="font-mono font-semibold text-text-secondary">{{ fontSize }}px</output>
                    <span>较大</span>
                  </div>
                </section>

                <section class="rounded-[20px] border border-subtle bg-card p-5 shadow-card">
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <h3 class="text-sm font-bold tracking-wide text-text-secondary">界面动效</h3>
                      <p class="mt-2 text-sm font-light leading-7 text-text-muted">
                        默认保留抽屉、卡片和面板切换反馈；需要静态阅读时可临时减少动效。
                      </p>
                    </div>
                    <button
                      type="button"
                      class="focus-ring rounded-full border px-4 py-2 text-xs font-semibold tracking-wide transition-all duration-200"
                      :class="reduceMotion
                        ? 'border-secondary/35 bg-secondary-soft text-secondary'
                        : 'border-subtle bg-card text-text-secondary hover:border-secondary/40 hover:text-secondary hover:bg-card-hover'"
                      @click="$emit('toggle-motion')"
                    >
                      {{ reduceMotion ? "恢复动效" : "减少动效" }}
                    </button>
                  </div>
                </section>
=======
            <div class="grid grid-cols-3 border-b border-subtle bg-space-surface/55 px-5 py-4">
              <div v-for="stat in pathStats" :key="stat.label" class="min-w-0 px-3 first:pl-0 last:pr-0">
                <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">{{ stat.label }}</p>
                <p class="mt-1 truncate text-base font-black text-text-primary">{{ stat.value }}</p>
>>>>>>> origin/main
              </div>
                </div>
              </transition>
            </div>

<<<<<<< HEAD
            <button
              ref="closeButton"
              type="button"
              class="focus-ring absolute right-4 top-4 rounded-full border border-subtle/70 bg-card/82 p-2 text-text-muted shadow-sm backdrop-blur-sm transition hover:bg-card-hover hover:text-text-primary"
              :aria-label="activePanel === 'settings' ? '关闭显示设置' : '关闭学习控制台'"
              @click="$emit('close')"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 6 6 18" />
                <path d="M6 6l12 12" />
              </svg>
            </button>
=======
            <div class="aurora-scroll min-h-0 flex-1 overflow-y-auto px-5 py-5">
              <KnowledgeTree
                :nodes="nodes"
                :current-node="currentNode"
                @select="$emit('select-node', $event)"
              />
              <p v-if="!nodes.length" class="px-2 py-8 text-center text-sm leading-7 text-text-muted">
                完成入学诊断后，学习路径会显示在这里。
              </p>
            </div>
>>>>>>> origin/main
          </div>
        </aside>
      </transition>
    </div>
  </transition>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import KnowledgeTree from "./KnowledgeTree.vue";
import IconTree from "./icons/IconTree.vue";

const props = defineProps({
  open: { type: Boolean, default: false },
  panelId: { type: String, default: "workspace-sidebar-drawer" },
  nodes: { type: Array, default: () => [] },
  currentNode: { type: String, default: "" },
});

const emit = defineEmits(["select-node", "close"]);

const drawerPanel = ref(null);
const closeButton = ref(null);
let previousBodyOverflow = "";
let previousFocusedElement = null;

const completedNodes = computed(() => (
  props.nodes.filter((node) => Number(node?.mastery ?? 0) >= 0.65).length
));

<<<<<<< HEAD
const panelTabs = [
  { key: "tree", label: "路径" },
  { key: "feedback", label: "协同" },
  { key: "radar", label: "成果" },
];

const titles = {
  tree: "知识路径",
  radar: "学习成果",
  feedback: "智能体协同",
  settings: "工作台设置",
};

const descriptions = {
  tree: "追踪学习拓扑，查看掌握状态，并直接跳转到下一步更值得投入的节点。",
  radar: "结合最近诊断与能力雷达，快速查看本轮学习产生的有效成果。",
  feedback: "集中查看画像、规划、生成、校验与评估智能体的协作过程。",
  settings: "围绕当前工作台会话微调主题、对比度、字号和动效节奏。",
};

const completedNodes = computed(() =>
  props.nodes.filter((node) => node.mastery >= 0.65).length,
);

const currentNodeMeta = computed(() =>
  props.nodes.find((node) => node.id === props.currentNode) ?? null,
);

const nextPendingNode = computed(() =>
  props.nodes.find((node) => node.id !== props.currentNode && node.mastery < 0.65) ?? null,
);

const radarDimensions = [
  { key: "concept", label: "概念理解力" },
  { key: "engineering", label: "代码工程力" },
  { key: "logic", label: "逻辑推理力" },
  { key: "recovery", label: "纠错韧性" },
  { key: "time", label: "时间管理力" },
];

function radarBarClass(value) {
  if (value >= 0.7) return "bg-success";
  if (value >= 0.5) return "bg-primary";
  if (value >= 0.35) return "bg-warning";
  return "bg-error";
}

function radarTextClass(value) {
  if (value >= 0.7) return "text-success";
  if (value >= 0.5) return "text-primary";
  if (value >= 0.35) return "text-warning";
  return "text-error";
}
=======
const currentNodeMeta = computed(() => (
  props.nodes.find((node) => node.id === props.currentNode) ?? null
));

const nextPendingNode = computed(() => (
  props.nodes.find((node) => node.id !== props.currentNode && Number(node?.mastery ?? 0) < 0.65) ?? null
));
>>>>>>> origin/main

const pathStats = computed(() => [
  { label: "已达标", value: `${completedNodes.value}/${props.nodes.length || 0}` },
  {
    label: "当前掌握",
    value: currentNodeMeta.value
      ? `${Math.round(Number(currentNodeMeta.value.mastery ?? 0) * 100)}%`
      : "--",
  },
  {
    label: "下一建议",
    value: nextPendingNode.value?.title || "已完成",
  },
]);

<<<<<<< HEAD
const panelIcon = computed(() => panelIcons[props.activePanel] ?? IconSettings);
const panelTitle = computed(() => titles[props.activePanel] ?? "工作台");
const panelDescription = computed(() => descriptions[props.activePanel] ?? "学习控制台。");
const panelEyebrow = computed(() => (
  props.activePanel === "settings" ? "显示偏好" : "学习控制台"
));
const panelSurfaceStyle = computed(() => ({
  backgroundColor: theme.value === "light" ? "#f7f3e8" : "#0b1120",
}));

=======
>>>>>>> origin/main
watch(
  () => props.open,
  async (isOpen) => {
    if (typeof window !== "undefined") {
      if (isOpen) window.addEventListener("keydown", handleKeydown);
      else window.removeEventListener("keydown", handleKeydown);
    }

    if (typeof document === "undefined") return;

    if (isOpen) {
      previousFocusedElement = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      previousBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      await nextTick();
      closeButton.value?.focus();
      return;
    }

    document.body.style.overflow = previousBodyOverflow;
    restoreFocus();
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (typeof window !== "undefined") window.removeEventListener("keydown", handleKeydown);
  if (typeof document !== "undefined") document.body.style.overflow = previousBodyOverflow;
});

function handleKeydown(event) {
  if (!props.open) return;
  if (event.key === "Escape") {
    event.preventDefault();
    emit("close");
    return;
  }
  if (event.key === "Tab") trapFocus(event);
}

function restoreFocus() {
  if (previousFocusedElement instanceof HTMLElement && previousFocusedElement.isConnected) {
    previousFocusedElement.focus();
  }
  previousFocusedElement = null;
}

function trapFocus(event) {
  if (!(drawerPanel.value instanceof HTMLElement)) return;
  const focusable = Array.from(drawerPanel.value.querySelectorAll(
    "button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex='-1'])",
  )).filter((element) => element instanceof HTMLElement);

  if (!focusable.length) {
    event.preventDefault();
    drawerPanel.value.focus();
    return;
  }

  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && (document.activeElement === first || !drawerPanel.value.contains(document.activeElement))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (document.activeElement === last || !drawerPanel.value.contains(document.activeElement))) {
    event.preventDefault();
    first.focus();
  }
}
</script>

<style scoped>
<<<<<<< HEAD
.sidebar-drawer-layer {
  z-index: var(--z-modal-backdrop);
=======
.drawer-surface {
  isolation: isolate;
}

.drawer-surface__glow {
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-primary-soft) 70%, transparent), transparent 34%);
}

.drawer-backdrop-enter-active,
.drawer-backdrop-leave-active {
  transition: opacity 220ms ease;
}

.drawer-backdrop-enter-from,
.drawer-backdrop-leave-to {
  opacity: 0;
}

.drawer-panel-enter-active,
.drawer-panel-leave-active {
  transition: transform 260ms cubic-bezier(0.16, 1, 0.3, 1), opacity 220ms ease;
}

.drawer-panel-enter-from,
.drawer-panel-leave-to {
  transform: translateX(-24px);
  opacity: 0;
>>>>>>> origin/main
}

@media (max-width: 767px) {
  .drawer-surface {
    top: max(0.75rem, env(safe-area-inset-top, 0px));
    right: max(0.75rem, env(safe-area-inset-right, 0px));
    bottom: max(0.75rem, env(safe-area-inset-bottom, 0px));
    left: max(0.75rem, env(safe-area-inset-left, 0px));
    border-radius: var(--radius-lg);
  }
}

<<<<<<< HEAD
.drawer-surface {
  isolation: isolate;
}

.drawer-surface__glow {
  background:
    radial-gradient(circle at top, rgba(63, 222, 205, 0.1), transparent 34%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.14), rgba(255, 255, 255, 0.05));
}

.drawer-backdrop-enter-active,
.drawer-backdrop-leave-active {
  transition: opacity 280ms ease;
}

.drawer-backdrop-enter-from,
.drawer-backdrop-leave-to {
  opacity: 0;
}

.drawer-panel-enter-active,
.drawer-panel-leave-active {
  transition: transform 320ms cubic-bezier(0.16, 1, 0.3, 1), opacity 260ms ease;
}

.drawer-panel-enter-from,
.drawer-panel-leave-to {
  transform: translateX(24px) scale(0.98);
  opacity: 0;
}

.drawer-content-enter-active {
  transition:
    opacity 220ms var(--ease-standard),
    transform 260ms var(--ease-emphasized),
    filter 220ms var(--ease-standard);
}

.drawer-content-leave-active {
  transition:
    opacity 120ms var(--ease-standard),
    transform 140ms var(--ease-standard);
}

.drawer-content-enter-from {
  opacity: 0;
  transform: translateY(8px);
  filter: blur(2px);
}

.drawer-content-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-primary);
  box-shadow: 0 0 12px var(--color-primary-soft);
  cursor: pointer;
}

input[type="range"]::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-primary);
  box-shadow: 0 0 12px var(--color-primary-soft);
  cursor: pointer;
  border: none;
=======
@media (prefers-reduced-motion: reduce) {
  .drawer-backdrop-enter-active,
  .drawer-backdrop-leave-active,
  .drawer-panel-enter-active,
  .drawer-panel-leave-active {
    transition-duration: 0.01ms;
  }
>>>>>>> origin/main
}
</style>
