<template>
  <section class="relative flex h-full min-h-0 flex-col px-8 pb-8">
    <header class="pb-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p class="text-[10px] font-black uppercase tracking-[-0.05em] text-[#4A4F68]">MULTIMODAL CANVAS</p>
          <h2 class="mt-2 text-[28px] font-black uppercase tracking-[-0.05em] text-[#F1F4FC]">{{ nodeTitle || "Awaiting Assembly" }}</h2>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="focus-ring rounded-full border border-white/[0.04] px-3 py-2 text-[11px] font-black uppercase tracking-[0.14em] text-[#7A8096] transition hover:border-aurora-mint/25 hover:text-[#E9EDF8]"
            @click="isExpanded = !isExpanded"
          >
            {{ isExpanded ? "Compact View" : "Expand Matrix" }}
          </button>
          <button
            type="button"
            class="focus-ring rounded-full border border-white/[0.04] px-3 py-2 text-[11px] font-black uppercase tracking-[0.14em] text-[#7A8096] transition hover:border-aurora-mint/25 hover:text-[#E9EDF8]"
            @click="focusMode = !focusMode"
          >
            {{ focusMode ? "Exit Focus" : "Focus Mode" }}
          </button>
        </div>
      </div>

      <div class="mt-5 flex flex-wrap gap-2">
        <button
          v-for="node in pathNodes"
          :key="node.id"
          type="button"
          class="focus-ring rounded-full border px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.14em] transition"
          :class="node.id === currentNode
            ? 'border-aurora-purple/35 text-[#ECEFFC]'
            : node.mastery >= 0.65
              ? 'border-aurora-mint/28 text-aurora-mint'
              : 'border-white/[0.04] text-[#69708A]'"
          @click="$emit('select-node', node.id)"
        >
          {{ node.title }}
        </button>
      </div>
    </header>

    <div class="aurora-scroll relative flex-1 overflow-y-auto">
      <div v-if="!cards.length && !loading" class="flex h-full min-h-[420px] items-center justify-center">
        <div class="flex flex-col items-center text-center">
          <div class="relative mb-5 flex h-20 w-20 items-center justify-center rounded-full">
            <div class="absolute inset-0 rounded-full bg-aurora-purple/10 blur-xl animate-halo" />
            <svg
              width="48"
              height="48"
              viewBox="0 0 48 48"
              fill="none"
              class="relative text-aurora-purple"
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
          <p class="font-mono text-[12px] uppercase tracking-[0.22em] text-[#4A4F68]">
            Multi-agent topology core waiting for assembly.
          </p>
          <p class="mt-2 max-w-[42ch] font-mono text-[12px] leading-6 text-[#4A4F68]">
            Current node resources have not been materialized yet. Select a path node or wait for the orchestration pipeline.
          </p>
        </div>
      </div>

      <div
        class="mx-auto grid max-w-6xl grid-cols-1 gap-6 transition-all duration-500 ease-in-out md:grid-cols-2 xl:grid-cols-3"
        :class="isExpanded ? 'scale-100' : 'scale-[0.992]'"
      >
        <div
          v-for="card in visibleCards"
          :key="card.resource_id"
          draggable="true"
          class="transition-all duration-500"
          :class="getGridSpanClass(card.card_type)"
          @dragstart="onDragStart(card.resource_id)"
          @dragover.prevent
          @drop="onDrop(card.resource_id)"
        >
          <ResourceCard
            :agent-name="agentLabel(card.card_type)"
            :title="cardLabel(card.card_type)"
            :progress-text="loading ? 'Mesh Sync' : 'Resource Ready'"
            :progress="loading ? progressHint(card.card_type) : 100"
            :is-ready="!loading"
            :is-active="card.resource_id === activeCardId"
            :ready-class="card.card_type === 'diagnostic_quiz' ? 'bg-aurora-purple' : 'bg-aurora-mint'"
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
                    class="rounded-[18px] border border-white/[0.04] bg-white/[0.015] p-4 shadow-[inset_0_1px_8px_rgba(0,0,0,0.35)]"
                  >
                    <p class="text-sm font-medium text-[#F0F3FB]">{{ question.prompt }}</p>
                    <div class="mt-3 space-y-2">
                      <button
                        v-for="(option, optionIndex) in question.options"
                        :key="`${question.id}-${optionIndex}`"
                        type="button"
                        class="focus-ring w-full rounded-[16px] border px-3 py-2 text-left text-sm font-light transition"
                        :class="answerClass(question.id, optionIndex)"
                        @click="setAnswer(question.id, optionIndex)"
                      >
                        {{ option }}
                      </button>
                    </div>
                  </div>

                  <div class="flex flex-wrap items-center justify-between gap-3 rounded-[18px] border border-white/[0.04] bg-white/[0.015] p-4 shadow-[inset_0_1px_8px_rgba(0,0,0,0.35)]">
                    <div class="text-sm font-light text-[#7A8096]">
                      {{ submittedScore === null ? "Answer all prompts before dispatching the diagnostic score." : `Last diagnostic score ${Math.round(submittedScore * 100)}%` }}
                    </div>
                    <button
                      type="button"
                      class="focus-ring rounded-full border border-aurora-purple/18 bg-[linear-gradient(135deg,rgba(0,242,254,0.22),rgba(127,0,255,0.32))] px-4 py-2 text-[11px] font-black uppercase tracking-[0.14em] text-white transition active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
                      :disabled="!allAnswered || loading"
                      @click="submitQuizScore"
                    >
                      Submit Diagnostic
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
        <span class="text-[10px] font-black uppercase tracking-[0.16em] text-[#4A4F68]">Minimized</span>
        <button
          v-for="card in minimizedCards"
          :key="card.resource_id"
          type="button"
          class="focus-ring rounded-full border border-white/[0.04] px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-[#7A8096] transition hover:border-aurora-mint/25 hover:text-[#E9EDF8]"
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
      return "col-span-1 xl:col-span-2";
    case "code_snippet":
      return "col-span-1 md:col-span-2 xl:col-span-3";
    case "interactive_exercise":
    case "diagnostic_quiz":
    default:
      return "col-span-1";
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
    ? "border-aurora-mint/30 bg-aurora-mint/8 text-[#F0F3FB]"
    : "border-white/[0.04] bg-transparent text-[#8A90A8] hover:border-aurora-purple/25 hover:text-[#E9EDF8]";
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
