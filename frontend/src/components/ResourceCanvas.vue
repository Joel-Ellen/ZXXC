<template>
  <section class="dot-grid relative flex h-full min-h-0 flex-col px-8 pb-8">
    <header class="pb-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">多模态画布</p>
          <h2 class="gradient-text mt-2 text-[28px] font-black tracking-tight">{{ nodeTitle || "等待装配" }}</h2>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="focus-ring rounded-full border border-subtle bg-card px-3.5 py-2 text-[11px] font-semibold uppercase tracking-[0.10em] text-text-muted transition-all duration-200 hover:border-primary/30 hover:text-primary hover:bg-card-hover active:scale-95"
            @click="isExpanded = !isExpanded"
          >
            {{ isExpanded ? "紧凑视图" : "展开矩阵" }}
          </button>
          <button
            type="button"
            class="focus-ring rounded-full border border-subtle bg-card px-3.5 py-2 text-[11px] font-semibold uppercase tracking-[0.10em] text-text-muted transition-all duration-200 hover:border-secondary/30 hover:text-secondary hover:bg-card-hover active:scale-95"
            @click="focusMode = !focusMode"
          >
            {{ focusMode ? "退出聚焦" : "聚焦模式" }}
          </button>
        </div>
      </div>

      <div class="mt-5 flex flex-wrap gap-2">
        <button
          v-for="node in pathNodes"
          :key="node.id"
          type="button"
          class="focus-ring rounded-full border px-3.5 py-1.5 text-[11px] font-medium uppercase tracking-[0.10em] transition-all duration-200 active:scale-95"
          :class="node.id === currentNode
            ? 'border-secondary/40 bg-secondary-soft text-secondary shadow-[0_0_12px_var(--color-secondary-soft)]'
            : node.mastery >= 0.65
              ? 'border-success/25 text-success hover:border-success/40 hover:bg-success-soft'
              : 'border-subtle text-text-muted hover:border-hover hover:text-text-secondary hover:bg-card-hover'"
          @click="$emit('select-node', node.id)"
        >
          {{ node.title }}
        </button>
      </div>
    </header>

    <div class="aurora-scroll relative flex-1 overflow-y-auto">
      <div v-if="!cards.length && !loading" class="flex h-full min-h-[420px] items-center justify-center">
        <div class="flex flex-col items-center text-center animate-fadeIn">
          <div class="relative mb-6 flex h-24 w-24 items-center justify-center rounded-full">
            <div class="absolute inset-0 rounded-full bg-secondary/15 blur-2xl animate-halo" />
            <div class="absolute inset-0 rounded-full border border-secondary/20 animate-spin-slow" />
            <svg
              width="52"
              height="52"
              viewBox="0 0 48 48"
              fill="none"
              class="relative text-secondary"
              aria-hidden="true"
            >
              <circle cx="24" cy="24" r="6" stroke="currentColor" stroke-width="1.5" />
              <circle cx="24" cy="10" r="3.5" stroke="currentColor" stroke-width="1.25" opacity="0.65" />
              <circle cx="36" cy="30" r="3.5" stroke="currentColor" stroke-width="1.25" opacity="0.65" />
              <circle cx="12" cy="30" r="3.5" stroke="currentColor" stroke-width="1.25" opacity="0.65" />
              <path d="M24 17V20" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
              <path d="M29 27l4 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
              <path d="M19 27l-4 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </div>
          <p class="font-mono text-[12px] uppercase tracking-[0.22em] text-text-muted">
            多智能体拓扑核心等待装配。
          </p>
          <p class="mt-2 max-w-[46ch] font-mono text-[12px] leading-6 text-text-muted">
            当前节点资源尚未生成。请选择左侧路径节点，或等待编排流水线完成。
          </p>
        </div>
      </div>

      <div
        class="mx-auto grid max-w-6xl grid-cols-1 gap-5 transition-all duration-500 ease-snap md:grid-cols-12"
        :class="isExpanded ? 'scale-100' : 'scale-[0.992]'">
        <div
          v-for="(card, index) in visibleCards"
          :key="card.resource_id"
          draggable="true"
          class="animate-cardIn transition-all duration-500"
          :style="{ animationDelay: `${index * 60}ms` }"
          :class="getGridSpanClass(card.card_type)"
          @dragstart="onDragStart(card.resource_id)"
          @dragover.prevent
          @drop="onDrop(card.resource_id)"
        >
          <ResourceCard
            :agent-name="agentLabel(card.card_type)"
            :title="cardLabel(card.card_type)"
            :progress-text="loading ? '网格同步' : '资源就绪'"
            :progress="loading ? progressHint(card.card_type) : 100"
            :is-ready="!loading"
            :is-active="card.resource_id === activeCardId"
            :color="cardColor(card.card_type)"
            @pin="pinCard(card.resource_id)"
            @minimize="minimizeCard(card.resource_id)"
          >
            <template #content>
              <div class="space-y-5">
                <MarkdownContent
                  v-if="card.card_type !== 'diagnostic_quiz'"
                  :content="card.content"
                />

                <div v-else class="space-y-4">
                  <MarkdownContent :content="card.content" />
                  <div
                    v-for="question in quizQuestions"
                    :key="question.id"
                    class="rounded-[18px] border border-subtle bg-card p-4 shadow-card"
                  >
                    <p class="text-sm font-medium text-text-primary">{{ question.prompt }}</p>
                    <div class="mt-3 space-y-2">
                      <button
                        v-for="(option, optionIndex) in question.options"
                        :key="`${question.id}-${optionIndex}`"
                        type="button"
                        class="focus-ring w-full rounded-[14px] border px-3 py-2.5 text-left text-sm font-light transition-all duration-200 active:scale-[0.99]"
                        :class="answerClass(question.id, optionIndex)"
                        @click="setAnswer(question.id, optionIndex)"
                      >
                        {{ option }}
                      </button>
                    </div>
                  </div>

                  <div class="flex flex-wrap items-center justify-between gap-3 rounded-[18px] border border-subtle bg-card p-4 shadow-card">
                    <div class="text-sm font-light text-text-muted">
                      {{ submittedScore === null ? "请先回答所有题目，再提交诊断得分。" : `上次诊断得分 ${Math.round(submittedScore * 100)}%` }}
                    </div>
                    <button
                      type="button"
                      class="focus-ring btn-capsule"
                      :disabled="!allAnswered || loading"
                      @click="submitQuizScore"
                    >
                      提交诊断
                    </button>
                  </div>
                </div>
              </div>
            </template>
          </ResourceCard>
        </div>
      </div>
    </div>

    <footer v-if="minimizedCards.length" class="pt-5">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">已最小化</span>
        <button
          v-for="card in minimizedCards"
          :key="card.resource_id"
          type="button"
          class="focus-ring rounded-full border border-subtle bg-card px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.10em] text-text-muted transition-all duration-200 hover:border-primary/30 hover:text-primary hover:bg-card-hover active:scale-95"
          @click="restoreCard(card.resource_id)"
        >
          {{ cardLabel(card.card_type) }}
        </button>
      </div>
    </footer>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import MarkdownContent from "./MarkdownContent.vue";
import ResourceCard from "./ResourceCard.vue";

const props = defineProps({
  cards: { type: Array, default: () => [] },
  currentNode: { type: String, default: "" },
  nodeTitle: { type: String, default: "" },
  pathNodes: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  getCardLabel: { type: Function, required: true },
  getAgentLabel: { type: Function, required: true },
  buildQuiz: { type: Function, required: true },
});

const emit = defineEmits(["submit-quiz", "select-node"]);

const orderedIds = ref([]);
const minimizedIds = ref([]);
const activeCardId = ref("");
const dragId = ref("");
const focusMode = ref(false);
const isExpanded = ref(false);
const answers = ref({});
const submittedScore = ref(null);

watch(
  () => props.cards,
  (cards) => {
    const nextIds = cards.map((card) => card.resource_id);
    orderedIds.value = nextIds;
    minimizedIds.value = [];
    activeCardId.value = nextIds[0] ?? "";
    focusMode.value = false;
    answers.value = {};
    submittedScore.value = null;
  },
  { immediate: true },
);

const sortedCards = computed(() => {
  const orderIndex = new Map(orderedIds.value.map((id, index) => [id, index]));
  return [...props.cards].sort(
    (left, right) =>
      (orderIndex.get(left.resource_id) ?? Number.MAX_SAFE_INTEGER) -
      (orderIndex.get(right.resource_id) ?? Number.MAX_SAFE_INTEGER),
  );
});

const minimizedCards = computed(() =>
  sortedCards.value.filter((card) => minimizedIds.value.includes(card.resource_id)),
);

const visibleCards = computed(() => {
  const base = sortedCards.value.filter((card) => !minimizedIds.value.includes(card.resource_id));
  if (focusMode.value && activeCardId.value) {
    return base.filter((card) => card.resource_id === activeCardId.value);
  }
  return base;
});

const quizCard = computed(() =>
  props.cards.find((card) => card.card_type === "diagnostic_quiz"),
);

const quizQuestions = computed(() => props.buildQuiz(quizCard.value?.content ?? ""));
const allAnswered = computed(
  () => quizQuestions.value.length > 0 && quizQuestions.value.every((question) => answers.value[question.id] !== undefined),
);

function cardLabel(cardType) {
  return props.getCardLabel(cardType);
}

function agentLabel(cardType) {
  return props.getAgentLabel(cardType);
}

function cardColor(cardType) {
  switch (cardType) {
    case "concept_map": return "primary";
    case "code_snippet": return "info";
    case "interactive_exercise": return "tertiary";
    case "video_summary": return "secondary";
    case "diagnostic_quiz": return "warning";
    default: return "primary";
  }
}

function progressHint(cardType) {
  if (cardType === "diagnostic_quiz") {
    return 72;
  }
  if (cardType === "code_snippet") {
    return 58;
  }
  return 84;
}

function getGridSpanClass(cardType) {
  switch (cardType) {
    case "concept_map":
    case "video_summary":
      return "col-span-1 md:col-span-6 xl:col-span-6";
    case "code_snippet":
      return "col-span-1 md:col-span-12 xl:col-span-12";
    case "interactive_exercise":
    case "diagnostic_quiz":
    default:
      return "col-span-1 md:col-span-6";
  }
}

function pinCard(cardId) {
  const next = orderedIds.value.filter((id) => id !== cardId);
  orderedIds.value = [cardId, ...next];
  activeCardId.value = cardId;
}

function minimizeCard(cardId) {
  if (!minimizedIds.value.includes(cardId)) {
    minimizedIds.value = [...minimizedIds.value, cardId];
  }
  if (activeCardId.value === cardId) {
    const fallback = orderedIds.value.find((id) => !minimizedIds.value.includes(id) && id !== cardId);
    activeCardId.value = fallback ?? "";
  }
}

function restoreCard(cardId) {
  minimizedIds.value = minimizedIds.value.filter((id) => id !== cardId);
  activeCardId.value = cardId;
}

function onDragStart(cardId) {
  dragId.value = cardId;
}

function onDrop(targetId) {
  if (!dragId.value || dragId.value === targetId) {
    return;
  }
  const next = orderedIds.value.filter((id) => id !== dragId.value);
  const targetIndex = next.indexOf(targetId);
  next.splice(targetIndex, 0, dragId.value);
  orderedIds.value = next;
  activeCardId.value = dragId.value;
  dragId.value = "";
}

function setAnswer(questionId, optionIndex) {
  answers.value = {
    ...answers.value,
    [questionId]: optionIndex,
  };
}

function answerClass(questionId, optionIndex) {
  const selected = answers.value[questionId] === optionIndex;
  return selected
    ? "border-primary/30 bg-primary-soft text-primary"
    : "border-subtle bg-transparent text-text-secondary hover:border-secondary/25 hover:text-text-primary hover:bg-card-hover";
}

function submitQuizScore() {
  let correct = 0;
  quizQuestions.value.forEach((question) => {
    if (answers.value[question.id] === question.answer) {
      correct += 1;
    }
  });
  const score = quizQuestions.value.length ? correct / quizQuestions.value.length : 0;
  submittedScore.value = score;
  emit("submit-quiz", score);
}
</script>

<style scoped>
.dot-grid {
  background-image: radial-gradient(circle, color-mix(in srgb, var(--text-muted) 10%, transparent) 1px, transparent 1px);
  background-size: 28px 28px;
}
</style>
