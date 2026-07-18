<template>
  <transition name="drawer-backdrop">
    <div v-if="open" class="fixed inset-0 z-40 lg:z-30">
      <button
        type="button"
        class="absolute inset-0 w-full bg-black/42 backdrop-blur-[3px] lg:bg-[color:rgba(8,14,28,0.16)] lg:backdrop-blur-[1px]"
        aria-label="关闭学习路径"
        @click="$emit('close')"
      />

      <transition name="drawer-panel">
        <aside
          v-if="open"
          :id="panelId"
          ref="drawerPanel"
          class="drawer-surface absolute bottom-4 left-4 right-4 top-24 z-10 flex overflow-hidden rounded-[24px] border border-[color:rgba(255,255,255,0.55)] bg-space-panel shadow-[0_28px_80px_rgba(15,23,42,0.24)] lg:inset-y-4 lg:left-[76px] lg:right-auto lg:top-4 lg:w-[408px] lg:rounded-l-none lg:border-l-0"
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
              <div class="min-w-0 flex-1 pr-8">
                <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">课程路径</p>
                <h2 id="learning-path-title" class="mt-1.5 text-[28px] font-black tracking-tight text-text-primary">学习节点</h2>
                <p class="mt-2 max-w-[34ch] text-sm font-light leading-7 text-text-muted">
                  查看真实掌握状态，并直接跳转到下一步值得投入的节点。
                </p>
              </div>
              <button
                ref="closeButton"
                type="button"
                class="focus-ring absolute right-4 top-4 rounded-full border border-subtle/70 bg-card/82 p-2 text-text-muted shadow-sm transition hover:bg-card-hover hover:text-text-primary"
                aria-label="关闭学习路径"
                @click="$emit('close')"
              >
                <span aria-hidden="true">×</span>
              </button>
            </header>

            <div class="grid grid-cols-3 border-b border-subtle bg-space-surface/55 px-5 py-4">
              <div v-for="stat in pathStats" :key="stat.label" class="min-w-0 px-3 first:pl-0 last:pr-0">
                <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">{{ stat.label }}</p>
                <p class="mt-1 truncate text-base font-black text-text-primary">{{ stat.value }}</p>
              </div>
            </div>

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

const currentNodeMeta = computed(() => (
  props.nodes.find((node) => node.id === props.currentNode) ?? null
));

const nextPendingNode = computed(() => (
  props.nodes.find((node) => node.id !== props.currentNode && Number(node?.mastery ?? 0) < 0.65) ?? null
));

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

@media (prefers-reduced-motion: reduce) {
  .drawer-backdrop-enter-active,
  .drawer-backdrop-leave-active,
  .drawer-panel-enter-active,
  .drawer-panel-leave-active {
    transition-duration: 0.01ms;
  }
}
</style>
