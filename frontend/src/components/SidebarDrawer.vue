<template>
  <transition name="drawer-fade">
    <div
      v-if="open"
      class="path-drawer-layer fixed inset-0"
      @click.self="$emit('close')"
    >
      <button
        type="button"
        class="path-drawer-layer__backdrop"
        aria-label="关闭学习路径"
        @click="$emit('close')"
      />

      <aside
        :id="panelId"
        ref="drawerPanel"
        class="path-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="path-drawer-title"
        tabindex="-1"
      >
        <header class="path-drawer__header">
          <div class="path-drawer__heading">
            <p>课程路径</p>
            <h2 id="path-drawer-title">学习节点</h2>
          </div>
          <div class="path-drawer__summary">
            <span>{{ completedCount }}/{{ nodes.length }}</span>
            <button
              ref="closeButton"
              type="button"
              class="path-drawer__close focus-ring"
              aria-label="关闭学习路径"
              @click="$emit('close')"
            >
              ×
            </button>
          </div>
        </header>

        <nav class="path-drawer__list" aria-label="学习节点列表">
          <button
            v-for="(node, index) in nodes"
            :key="node.id"
            type="button"
            class="path-drawer__node focus-ring"
            :class="nodeClass(node)"
            :aria-current="node.id === currentNode ? 'step' : undefined"
            @click="$emit('select-node', node.id)"
          >
            <span class="path-drawer__order">{{ nodeOrder(node, index) }}</span>
            <span class="path-drawer__node-copy">
              <strong>{{ node.title }}</strong>
              <span>{{ nodeState(node) }}</span>
            </span>
            <span class="path-drawer__mastery">{{ mastery(node) }}%</span>
          </button>

          <p v-if="!nodes.length" class="path-drawer__empty">
            完成入学诊断后，学习路径会显示在这里。
          </p>
        </nav>
      </aside>
    </div>
  </transition>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps({
  open: { type: Boolean, default: false },
  panelId: { type: String, default: "workspace-sidebar-drawer" },
  nodes: { type: Array, default: () => [] },
  currentNode: { type: String, default: "" },
});

const emit = defineEmits([
  "select-node",
  "close",
]);

const drawerPanel = ref(null);
const closeButton = ref(null);
let previousBodyOverflow = "";
let previousFocusedElement = null;

const completedCount = computed(() => (
  props.nodes.filter((node) => mastery(node) >= 65).length
));

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
    if (previousFocusedElement instanceof HTMLElement && previousFocusedElement.isConnected) {
      previousFocusedElement.focus();
    }
    previousFocusedElement = null;
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown);
  document.body.style.overflow = previousBodyOverflow;
});

function mastery(node) {
  return Math.max(0, Math.min(100, Math.round(Number(node?.mastery ?? 0) * 100)));
}

function nodeOrder(node, index) {
  const order = Number(node?.order);
  return String(Number.isFinite(order) && order > 0 ? order : index + 1).padStart(2, "0");
}

function nodeState(node) {
  if (node?.id === props.currentNode) return "当前学习";
  if (mastery(node) >= 65) return "已完成";
  return "待学习";
}

function nodeClass(node) {
  if (node?.id === props.currentNode) return "is-current";
  if (mastery(node) >= 65) return "is-complete";
  return "";
}

function handleKeydown(event) {
  if (!props.open) return;
  if (event.key === "Escape") {
    event.preventDefault();
    emit("close");
    return;
  }
  if (event.key === "Tab") trapFocus(event);
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
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
</script>

<style scoped>
.path-drawer-layer {
  z-index: var(--z-drawer);
}

.path-drawer-layer__backdrop {
  position: absolute;
  inset: 0;
  width: 100%;
  border: 0;
  background: rgba(7, 31, 51, 0.34);
}

.path-drawer {
  position: absolute;
  inset: 3.75rem 0 0;
  display: flex;
  min-height: 0;
  flex-direction: column;
  border-top: 1px solid var(--border-subtle);
  background: var(--space-panel);
  outline: none;
}

.path-drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid var(--border-subtle);
  padding: 0.85rem 1rem;
}

.path-drawer__heading p {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 650;
}

.path-drawer__heading h2 {
  margin: 0.2rem 0 0;
  color: var(--text-primary);
  font-size: var(--font-size-lg);
  font-weight: 750;
}

.path-drawer__summary {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.72rem;
}

.path-drawer__close {
  display: inline-flex;
  width: 2.75rem;
  height: 2.75rem;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--space-elevated);
  color: var(--text-secondary);
  font-family: var(--font-sans);
  font-size: 1.4rem;
  line-height: 1;
}

.path-drawer__list {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 0.35rem;
  overflow-y: auto;
  padding: 0.75rem;
}

.path-drawer__node {
  display: grid;
  grid-template-columns: 2rem minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.6rem;
  min-height: 3.5rem;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  padding: 0.55rem 0.65rem;
  text-align: left;
}

.path-drawer__node:hover {
  background: var(--card-bg-hover);
}

.path-drawer__node.is-current {
  border-color: color-mix(in srgb, var(--color-primary) 25%, var(--border-subtle));
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
}

.path-drawer__order,
.path-drawer__mastery {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-variant-numeric: tabular-nums;
}

.path-drawer__node-copy {
  display: grid;
  min-width: 0;
  gap: 0.15rem;
}

.path-drawer__node-copy strong,
.path-drawer__node-copy span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.path-drawer__node-copy strong {
  color: var(--text-primary);
  font-size: 0.82rem;
  font-weight: 650;
}

.path-drawer__node-copy span {
  color: var(--text-muted);
  font-size: 0.7rem;
}

.path-drawer__node.is-complete .path-drawer__node-copy span,
.path-drawer__node.is-complete .path-drawer__mastery {
  color: var(--color-success-dark);
}

.path-drawer__empty {
  margin: 1rem;
  color: var(--text-muted);
  font-size: 0.82rem;
  line-height: 1.6;
}

.drawer-fade-enter-active,
.drawer-fade-leave-active {
  transition: opacity var(--duration-base) var(--ease-standard);
}

.drawer-fade-enter-from,
.drawer-fade-leave-to {
  opacity: 0;
}

@media (min-width: 768px) {
  .path-drawer {
    inset: 4rem auto 0 0;
    width: min(28rem, 70vw);
    border-right: 1px solid var(--border-subtle);
  }
}
</style>
