<template>
  <main
    :id="panelId"
    ref="paneRef"
    class="learning-pane safe-bottom"
    tabindex="-1"
    aria-label="学习资源区"
  >
    <ResourceCanvas
      ref="canvasRef"
      :cards="cards"
      :session-id="sessionId"
      :current-node="currentNode"
      :node-title="nodeTitle"
      :path-nodes="pathNodes"
      :loading="loading"
      :card-states="cardStates"
      :overall-progress="overallProgress"
      :mastered-count="masteredCount"
      :last-diagnostic="lastDiagnostic"
      :focus-card-type="focusCardType"
      :review-item-id="reviewItemId"
      :review-phase="reviewPhase"
      :filter-type="filterType"
      :get-card-label="getCardLabel"
      :get-agent-label="getAgentLabel"
      :build-quiz="buildQuiz"
      @submit-quiz="$emit('submit-quiz', $event)"
      @select-node="$emit('select-node', $event)"
      @refresh="$emit('refresh')"
      @generate-card="$emit('generate-card', $event)"
<<<<<<< HEAD
      @filter-change="$emit('filter-change', $event)"
=======
      @content-viewed="$emit('content-viewed', $event)"
      @hint-requested="$emit('hint-requested', $event)"
      @answer-selected="$emit('answer-selected', $event)"
      @code-run="$emit('code-run', $event)"
      @code-submitted="$emit('code-submitted', $event)"
      @open-review="$emit('open-review')"
      @prepare-review-retest="$emit('prepare-review-retest', $event)"
>>>>>>> origin/main
    />
  </main>
</template>

<script setup>
import { ref } from "vue";
import ResourceCanvas from "../ResourceCanvas.vue";

defineProps({
  panelId: { type: String, default: "workspace-learn-panel" },
  cards: { type: Array, default: () => [] },
  sessionId: { type: String, default: "" },
  currentNode: { type: String, default: "" },
  nodeTitle: { type: String, default: "" },
  pathNodes: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  cardStates: { type: Object, default: () => ({}) },
  overallProgress: { type: Number, default: 0 },
  masteredCount: { type: Number, default: 0 },
  lastDiagnostic: { type: Object, default: null },
  focusCardType: { type: String, default: "" },
  reviewItemId: { type: String, default: "" },
  reviewPhase: { type: String, default: "" },
  filterType: { type: String, default: "all" },
  getCardLabel: { type: Function, required: true },
  getAgentLabel: { type: Function, required: true },
  buildQuiz: { type: Function, required: true },
});

<<<<<<< HEAD
defineEmits(["submit-quiz", "select-node", "refresh", "generate-card", "filter-change"]);
=======
defineEmits([
  "submit-quiz",
  "select-node",
  "refresh",
  "generate-card",
  "content-viewed",
  "hint-requested",
  "answer-selected",
  "code-run",
  "code-submitted",
  "open-review",
  "prepare-review-retest",
]);
>>>>>>> origin/main

const paneRef = ref(null);
const canvasRef = ref(null);

function focus() {
  paneRef.value?.focus({ preventScroll: true });
}

function getElement() {
  return paneRef.value;
}

function scrollToAnnotations() {
  canvasRef.value?.scrollToAnnotations?.();
}

defineExpose({ focus, getElement, scrollToAnnotations });
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
