<template>
  <main
    :id="panelId"
    ref="paneRef"
    class="learning-pane safe-bottom"
    tabindex="-1"
    aria-label="学习资源区"
  >
    <ResourceCanvas
      :session-id="sessionId"
      :cards="cards"
      :current-node="currentNode"
      :node-title="nodeTitle"
      :path-nodes="pathNodes"
      :loading="loading"
      :overall-progress="overallProgress"
      :mastered-count="masteredCount"
      :last-diagnostic="lastDiagnostic"
      :filter-type="filterType"
      :get-card-label="getCardLabel"
      :get-agent-label="getAgentLabel"
      :build-quiz="buildQuiz"
      @submit-quiz="$emit('submit-quiz', $event)"
      @quiz-next="$emit('quiz-next', $event)"
      @select-node="$emit('select-node', $event)"
      @refresh="$emit('refresh')"
      @generate-card="$emit('generate-card', $event)"
      @filter-change="$emit('filter-change', $event)"
      @code-run="$emit('code-run', $event)"
      @code-submitted="$emit('code-submitted', $event)"
    />
  </main>
</template>

<script setup>
import { ref } from "vue";
import ResourceCanvas from "../ResourceCanvas.vue";

defineProps({
  panelId: { type: String, default: "workspace-learn-panel" },
  sessionId: { type: String, default: "" },
  cards: { type: Array, default: () => [] },
  currentNode: { type: String, default: "" },
  nodeTitle: { type: String, default: "" },
  pathNodes: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  overallProgress: { type: Number, default: 0 },
  masteredCount: { type: Number, default: 0 },
  lastDiagnostic: { type: Object, default: null },
  filterType: { type: String, default: "all" },
  getCardLabel: { type: Function, required: true },
  getAgentLabel: { type: Function, required: true },
  buildQuiz: { type: Function, required: true },
});

defineEmits([
  "submit-quiz",
  "quiz-next",
  "select-node",
  "refresh",
  "generate-card",
  "filter-change",
  "code-run",
  "code-submitted",
]);

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
.learning-pane {
  display: flex;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  outline: none;
}
</style>
