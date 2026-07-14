<template>
  <aside
    :id="panelId"
    ref="paneRef"
    class="tutor-pane safe-bottom"
    :class="{ 'is-probe': bootMode === 'probe' }"
    tabindex="-1"
    aria-label="辅导区"
  >
    <div class="tutor-pane__chat">
      <ChatArea
        :messages="messages"
        :boot-mode="bootMode"
        :probe="probe"
        :probe-collected="probeCollected"
        :probe-total="probeTotal"
        :is-submitting-probe="isSubmittingProbe"
        :busy="busy"
        :node-title="currentNodeTitle"
        :suggestions="suggestions"
        @send="$emit('send', $event)"
        @submit-probe="$emit('submit-probe', $event)"
      />
    </div>
  </aside>
</template>

<script setup>
import { ref } from "vue";
import ChatArea from "../ChatArea.vue";

defineProps({
  panelId: { type: String, default: "workspace-coach-panel" },
  currentNodeTitle: { type: String, default: "" },
  messages: { type: Array, default: () => [] },
  bootMode: { type: String, default: "loading" },
  probe: { type: Object, default: null },
  probeCollected: { type: Number, default: 0 },
  probeTotal: { type: Number, default: 6 },
  isSubmittingProbe: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  suggestions: { type: Array, default: () => [] },
});

defineEmits(["send", "submit-probe"]);

const paneRef = ref(null);

function focus() {
  paneRef.value?.focus({ preventScroll: true });
}

function getElement() {
  return paneRef.value;
}

defineExpose({ focus, getElement });
</script>

<style scoped>
.tutor-pane {
  display: flex;
  min-width: 0;
  min-height: 0;
  height: 100%;
  flex-direction: column;
  overflow: hidden;
  outline: none;
}

.tutor-pane__chat {
  display: flex;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}

@media (max-width: 767px) {
  .tutor-pane.is-probe .tutor-pane__chat :deep(> section) {
    padding: 0.75rem 1rem calc(env(safe-area-inset-bottom, 0px) + 4.5rem);
  }

  .tutor-pane.is-probe .tutor-pane__chat :deep(> section > header),
  .tutor-pane.is-probe .tutor-pane__chat :deep(> section > footer) {
    display: none;
  }

  .tutor-pane.is-probe .tutor-pane__chat :deep([data-chat-scroll="true"]) {
    padding-right: 0;
  }
}

@media (min-width: 1100px) {
  .tutor-pane {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    background: var(--space-panel);
  }
}
</style>
