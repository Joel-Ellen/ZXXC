<template>
  <!-- FAB 触发按钮（右下角固定） -->
  <div class="floating-chat-root">
    <button
      v-if="!isOpen"
      type="button"
      class="fab-btn btn-ripple focus-ring"
      :class="hasUnread ? 'fab-btn--unread' : ''"
      aria-label="打开学习托盘"
      @click="openTray"
    >
      <!-- Chat icon -->
      <IconChat :size="22" />
      <!-- Unread dot -->
      <span v-if="hasUnread" class="fab-unread-dot" aria-hidden="true" />
    </button>

    <!-- Draggable floating window -->
    <Teleport to="body">
      <div
        v-if="isOpen"
        ref="trayEl"
        class="tray-window animate-slideUp"
        :style="trayStyle"
        role="dialog"
        aria-label="学习托盘"
        aria-modal="false"
      >
        <!-- Drag handle / title bar -->
        <div
          class="tray-titlebar"
          @pointerdown.prevent="startDrag"
        >
          <div class="flex items-center gap-2 min-w-0">
            <span class="tray-dot tray-dot--primary animate-breathe" />
            <span class="tray-title">学习托盘</span>
            <span v-if="nodeTitle" class="tray-node-badge">{{ nodeTitle }}</span>
          </div>
          <div class="flex items-center gap-1 shrink-0">
            <button
              type="button"
              class="tray-ctrl-btn focus-ring"
              :title="isMinimized ? '展开' : '最小化'"
              @click="toggleMinimize"
            >
              <IconMinimize v-if="!isMinimized" :size="14" />
              <IconChevronUp v-else :size="14" />
            </button>
            <button
              type="button"
              class="tray-ctrl-btn tray-ctrl-btn--close focus-ring"
              title="关闭"
              @click="closeTray"
            >
              <IconClose :size="14" />
            </button>
          </div>
        </div>

        <!-- Chat content (collapsible) -->
        <div v-show="!isMinimized" class="tray-body">
          <ChatArea
            :messages="messages"
            :boot-mode="bootMode"
            :probe="probe"
            :probe-collected="probeCollected"
            :probe-total="probeTotal"
            :is-submitting-probe="isSubmittingProbe"
            :busy="busy"
            :node-title="nodeTitle"
            :suggestions="suggestions"
            @send="$emit('send', $event)"
            @submit-probe="$emit('submit-probe', $event)"
          />
        </div>

        <!-- Resize handle (bottom-right corner) -->
        <div class="tray-resize-handle" @pointerdown.prevent="startResize" aria-hidden="true" />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted } from "vue";
import ChatArea from "./ChatArea.vue";
import IconChat from "./icons/IconChat.vue";
import IconChevronUp from "./icons/IconChevronUp.vue";
import IconClose from "./icons/IconClose.vue";
import IconMinimize from "./icons/IconMinimize.vue";

const props = defineProps({
  messages:          { type: Array,   default: () => [] },
  bootMode:          { type: String,  default: "loading" },
  probe:             { type: Object,  default: null },
  probeCollected:    { type: Number,  default: 0 },
  probeTotal:        { type: Number,  default: 6 },
  isSubmittingProbe: { type: Boolean, default: false },
  busy:              { type: Boolean, default: false },
  nodeTitle:         { type: String,  default: "" },
  suggestions:       { type: Array,   default: () => [] },
});

const emit = defineEmits(["send", "submit-probe"]);

// ── Tray open/minimized state ──────────────────────────────────────────
const isOpen = ref(false);
const isMinimized = ref(false);

const hasUnread = computed(() =>
  props.messages.length > 0 && !isOpen.value,
);

function openTray() {
  isOpen.value = true;
  isMinimized.value = false;
}
function closeTray() {
  isOpen.value = false;
}
function toggleMinimize() {
  isMinimized.value = !isMinimized.value;
}

// ── Position & size ────────────────────────────────────────────────────
const trayEl = ref(null);
const posX = ref(null); // null = use default (bottom-right via CSS)
const posY = ref(null);
const trayW = ref(400);
const trayH = ref(520);

const trayStyle = computed(() => {
  const style = {
    width: `${trayW.value}px`,
    height: isMinimized.value ? "auto" : `${trayH.value}px`,
  };
  if (posX.value !== null && posY.value !== null) {
    style.left = `${posX.value}px`;
    style.top  = `${posY.value}px`;
    style.right = "auto";
    style.bottom = "auto";
  }
  return style;
});

// ── Drag ──────────────────────────────────────────────────────────────
let dragOffsetX = 0;
let dragOffsetY = 0;

function startDrag(e) {
  if (!trayEl.value) return;
  const rect = trayEl.value.getBoundingClientRect();
  dragOffsetX = e.clientX - rect.left;
  dragOffsetY = e.clientY - rect.top;
  // Capture pointer to track even outside the element
  trayEl.value.setPointerCapture(e.pointerId);
  trayEl.value.addEventListener("pointermove", onDrag);
  trayEl.value.addEventListener("pointerup", stopDrag, { once: true });
}

function onDrag(e) {
  const x = e.clientX - dragOffsetX;
  const y = e.clientY - dragOffsetY;
  const maxX = window.innerWidth  - trayW.value;
  const maxY = window.innerHeight - (isMinimized.value ? 48 : trayH.value);
  posX.value = Math.max(0, Math.min(x, maxX));
  posY.value = Math.max(0, Math.min(y, maxY));
}

function stopDrag() {
  trayEl.value?.removeEventListener("pointermove", onDrag);
}

// ── Resize ────────────────────────────────────────────────────────────
let resizeStartX = 0;
let resizeStartY = 0;
let resizeStartW = 0;
let resizeStartH = 0;

function startResize(e) {
  resizeStartX = e.clientX;
  resizeStartY = e.clientY;
  resizeStartW = trayW.value;
  resizeStartH = trayH.value;
  window.addEventListener("pointermove", onResize);
  window.addEventListener("pointerup", stopResize, { once: true });
}

function onResize(e) {
  const dw = e.clientX - resizeStartX;
  const dh = e.clientY - resizeStartY;
  trayW.value = Math.max(320, Math.min(resizeStartW + dw, 700));
  trayH.value = Math.max(360, Math.min(resizeStartH + dh, 800));
}

function stopResize() {
  window.removeEventListener("pointermove", onResize);
}

onUnmounted(() => {
  window.removeEventListener("pointermove", onResize);
  trayEl.value?.removeEventListener("pointermove", onDrag);
});
</script>

<style scoped>
/* ── FAB button ─────────────────────────────────────────────────────── */
.fab-btn {
  position: fixed;
  bottom: 1.75rem;
  right: 1.75rem;
  z-index: 900;
  width: 3.25rem;
  height: 3.25rem;
  border-radius: 50%;
  border: none;
  background: var(--color-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 6px 20px rgba(0, 107, 173, 0.36), 0 2px 6px rgba(0,0,0,0.14);
  transition: transform 200ms cubic-bezier(0.16,1,0.3,1), box-shadow 200ms ease;
  cursor: pointer;
}
.fab-btn:hover {
  transform: translateY(-2px) scale(1.04);
  box-shadow: 0 10px 28px rgba(0, 107, 173, 0.44), 0 3px 8px rgba(0,0,0,0.16);
}
.fab-btn:active {
  transform: scale(0.96);
}
.fab-btn--unread {
  animation: subtlePulse 2s ease-in-out infinite;
}
.fab-unread-dot {
  position: absolute;
  top: 0.35rem;
  right: 0.35rem;
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  background: var(--color-tertiary-dark);
  border: 2px solid var(--color-primary);
}

/* ── Floating tray window ───────────────────────────────────────────── */
.tray-window {
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  z-index: 901;
  width: 400px;
  height: 520px;
  border-radius: 20px;
  border: 1px solid var(--border-subtle);
  background: var(--space-panel);
  box-shadow:
    0 24px 60px rgba(0, 107, 173, 0.14),
    0 8px 24px rgba(0,0,0,0.10),
    inset 0 1px 0 rgba(255,255,255,0.70);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  /* prevent text selection during drag */
  user-select: none;
}

/* ── Title bar / drag handle ────────────────────────────────────────── */
.tray-titlebar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.625rem 0.875rem 0.5rem;
  border-bottom: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--color-primary-soft) 60%, var(--space-panel));
  cursor: grab;
  flex-shrink: 0;
}
.tray-titlebar:active { cursor: grabbing; }

.tray-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  flex-shrink: 0;
}
.tray-dot--primary {
  background: var(--color-primary);
  box-shadow: 0 0 8px var(--color-primary);
}

.tray-title {
  font-size: 0.6875rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-primary);
}

.tray-node-badge {
  font-size: 0.625rem;
  font-weight: 600;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
  max-width: 10rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Control buttons ─────────────────────────────────────────────────── */
.tray-ctrl-btn {
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  border: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease, transform 120ms ease;
}
.tray-ctrl-btn:hover {
  background: var(--card-bg-hover);
  color: var(--text-primary);
  transform: scale(1.08);
}
.tray-ctrl-btn--close:hover {
  background: var(--color-error-soft);
  color: var(--color-error);
}

/* ── Body ─────────────────────────────────────────────────────────────── */
.tray-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  /* allow inner scroll */
}

/* ── Resize handle ────────────────────────────────────────────────────── */
.tray-resize-handle {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 1.25rem;
  height: 1.25rem;
  cursor: se-resize;
  /* diagonal grip lines */
  background:
    linear-gradient(135deg,
      transparent 40%,
      var(--border-subtle) 40%, var(--border-subtle) 45%,
      transparent 45%, transparent 55%,
      var(--border-subtle) 55%, var(--border-subtle) 60%,
      transparent 60%, transparent 70%,
      var(--border-subtle) 70%, var(--border-subtle) 75%,
      transparent 75%
    );
}
</style>
