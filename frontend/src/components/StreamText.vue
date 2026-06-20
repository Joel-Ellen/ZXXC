<template>
  <div ref="container" class="stream-text text-text-primary" style="max-width: 80ch">
    {{ displayText }}
    <span v-if="isStreaming" class="stream-caret" />
  </div>
</template>

<script setup>
import { onUnmounted, ref, watch } from "vue";

const props = defineProps({
  tokenStream: {
    type: Object,
    default: () => ({}),
  },
});

const displayText = ref("");
let buffer = "";
let rafId = null;
const isStreaming = ref(true);

function renderLoop() {
  if (!buffer.length) {
    rafId = null;
    return;
  }

  const takeChars = buffer.length > 5 ? 3 : 1;
  displayText.value += buffer.slice(0, takeChars);
  buffer = buffer.slice(takeChars);
  rafId = requestAnimationFrame(renderLoop);
}

function schedule() {
  if (!rafId) {
    rafId = requestAnimationFrame(renderLoop);
  }
}

watch(
  () => props.tokenStream?.latest,
  (token) => {
    if (token) {
      buffer += token;
      schedule();
    }
  },
);

watch(
  () => props.tokenStream?.done,
  (done) => {
    if (done) {
      isStreaming.value = false;
    }
  },
  { immediate: true },
);

onUnmounted(() => {
  if (rafId) {
    cancelAnimationFrame(rafId);
  }
});
</script>

<style scoped>
.stream-text {
  white-space: pre-wrap;
  animation: fadeIn 0.15s ease-out;
}

.stream-caret {
  display: inline-block;
  width: 0.38rem;
  height: 0.95rem;
  margin-left: 0.18rem;
  vertical-align: middle;
  background: var(--color-primary);
  box-shadow: 0 0 10px var(--color-primary-soft);
  animation: pulseCaret 1s ease-in-out infinite;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

@keyframes pulseCaret {
  0%,
  100% {
    opacity: 0.35;
  }

  50% {
    opacity: 1;
  }
}
</style>
