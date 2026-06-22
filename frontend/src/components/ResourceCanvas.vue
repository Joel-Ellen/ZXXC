<template>
  <section class="dot-grid relative flex h-full min-h-0 flex-col px-4 pb-5 pt-4 sm:px-5 lg:px-8">
    <header class="pb-4 lg:pb-5">
      <div class="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_auto] 2xl:items-start">
        <div class="min-w-0">
          <p class="text-[10px] font-black uppercase tracking-[0.12em] text-text-muted sm:text-[11px]">课程学习区</p>
          <div class="mt-2 flex flex-wrap items-center gap-3">
            <h2 class="gradient-text truncate text-[22px] font-black tracking-tight sm:text-[24px] lg:text-[28px]">
              {{ nodeTitle || "等待装配" }}
            </h2>
            <span class="rounded-full border border-primary/20 bg-primary-soft px-3 py-1 text-[11px] font-semibold text-primary">
              {{ learningTone }}
            </span>
          </div>

          <div class="mt-4 hidden gap-2 xl:grid xl:grid-cols-4">
            <div
              v-for="stage in learningStages"
              :key="stage.label"
              class="rounded-[16px] border px-3 py-3"
              :class="stage.active ? 'border-primary/25 bg-primary-soft text-primary' : 'border-subtle bg-card text-text-muted'"
            >
              <p class="text-[10px] font-bold uppercase tracking-[0.12em]">{{ stage.label }}</p>
              <p class="mt-1 text-[12px] leading-5">{{ stage.detail }}</p>
            </div>
          </div>

          <div class="aurora-scroll mt-4 hidden gap-2 overflow-x-auto pb-1 sm:flex xl:hidden">
            <div
              v-for="stage in learningStages"
              :key="`mobile-${stage.label}`"
              class="shrink-0 rounded-full border px-3 py-2"
              :class="stage.active ? 'border-primary/25 bg-primary-soft text-primary' : 'border-subtle bg-card text-text-muted'"
            >
              <div class="flex items-center gap-1.5 whitespace-nowrap">
                <p class="text-[10px] font-bold uppercase tracking-[0.12em]">{{ stage.label }}</p>
                <p class="text-[10px] leading-5">{{ stage.detail }}</p>
              </div>
            </div>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2 2xl:justify-end">
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

      <div class="mt-4 hidden rounded-[18px] border border-subtle bg-card px-4 py-3 shadow-card sm:block xl:hidden">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">推荐下一步</p>
            <p class="mt-1 text-sm font-semibold text-text-primary">{{ recommendationTitle }}</p>
            <p class="mt-1 text-[11px] leading-5 text-text-muted">
              掌握 {{ currentMastery }}% · 材料 {{ cards.length }} 份 · {{ availableTypes.has("diagnostic_quiz") ? "可提交诊断" : "诊断待生成" }}
            </p>
          </div>
          <span class="rounded-full border border-subtle bg-space-surface/70 px-3 py-1 text-[11px] font-semibold text-text-secondary">
            {{ overallProgress }}%
          </span>
        </div>
      </div>

      <div class="mt-5 hidden gap-3 xl:grid xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div class="rounded-[22px] border border-subtle bg-card p-4 shadow-card">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div class="min-w-0">
              <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">推荐下一步</p>
              <p class="mt-2 text-base font-semibold text-text-primary">{{ recommendationTitle }}</p>
              <p class="mt-2 text-sm leading-6 text-text-muted">{{ recommendationDetail }}</p>
            </div>
            <div class="rounded-[18px] border border-subtle bg-space-surface/70 px-4 py-3 text-right">
              <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">当前掌握</p>
              <p class="mt-2 text-2xl font-black text-text-primary">{{ currentMastery }}%</p>
            </div>
          </div>
        </div>

        <div class="hidden gap-3 xl:grid xl:grid-cols-1 2xl:grid-cols-3">
          <div
            v-for="brief in learningBriefs"
            :key="brief.label"
            class="rounded-[20px] border border-subtle bg-card px-4 py-3 shadow-card"
          >
            <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">{{ brief.label }}</p>
            <p class="mt-2 text-lg font-black text-text-primary">{{ brief.value }}</p>
            <p class="mt-1 text-[11px] leading-5 text-text-muted">{{ brief.detail }}</p>
          </div>
        </div>
      </div>

      <div class="mt-4 hidden items-center justify-between gap-3 sm:flex sm:mt-5">
        <div class="min-w-0">
          <p class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">课程目录</p>
          <p class="mt-1 text-xs leading-5 text-text-muted">
            总进度 {{ overallProgress }}% · 已掌握 {{ masteredCount }} / {{ pathNodes.length }} · 当前节点掌握度 {{ currentMastery }}%
          </p>
        </div>
      </div>

      <div class="aurora-scroll mt-3 hidden gap-2 overflow-x-auto pb-1 sm:flex">
        <button
          v-for="node in pathNodes"
          :key="node.id"
          type="button"
          class="focus-ring shrink-0 rounded-full border px-3.5 py-1.5 text-[11px] font-medium tracking-[0.06em] transition-all duration-200 active:scale-95"
          :class="nodeChipClass(node)"
          @click="$emit('select-node', node.id)"
        >
          {{ node.title }}
        </button>
      </div>
    </header>

    <div class="aurora-scroll relative flex-1 overflow-y-auto">
      <div v-if="!cards.length && !loading" class="flex h-full min-h-[420px] items-center justify-center">
        <div class="flex max-w-[44ch] flex-col items-center text-center animate-fadeIn">
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
            当前学习节点等待装配
          </p>
          <p class="mt-2 font-mono text-[12px] leading-6 text-text-muted">
            请选择课程目录中的节点，或等待智能体完成资源生成。装配完成后会自动进入可学习状态。
          </p>
        </div>
      </div>

      <div
        class="mx-auto grid max-w-6xl grid-cols-1 gap-5 transition-all duration-500 ease-snap md:grid-cols-12"
        :class="isExpanded ? 'scale-100' : 'scale-[0.992]'"
      >
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
            :progress-text="loading ? '栅格同步' : '资源就绪'"
            :progress="loading ? progressHint(card.card_type) : 100"
            :is-ready="!loading"
            :is-active="card.resource_id === activeCardId"
            :is-expanded="isCardHydrated(card.resource_id)"
            :activatable="!loading"
            :color="cardColor(card.card_type)"
            @activate="activateCard(card.resource_id)"
            @pin="pinCard(card.resource_id)"
            @minimize="minimizeCard(card.resource_id)"
          >
            <template #content>
              <div v-if="!isCardHydrated(card.resource_id)" class="space-y-4">
                <div class="rounded-[18px] border border-subtle bg-space-surface/55 p-4 shadow-card">
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">
                    {{ previewLabel(card.card_type) }}
                  </p>

                  <pre
                    v-if="card.card_type === 'code_snippet'"
                    class="mt-3 overflow-x-auto rounded-[16px] border border-subtle/80 bg-[#08111f] px-4 py-3 text-xs leading-6 text-slate-100"
                  >{{ previewCode(card) }}</pre>

                  <p v-else class="mt-3 text-sm leading-7 text-text-secondary">
                    {{ previewText(card) }}
                  </p>
                </div>

                <button
                  type="button"
                  class="focus-ring rounded-full border border-primary/20 bg-primary-soft px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.10em] text-primary transition-all duration-200 hover:border-primary/35 hover:bg-primary-soft/80"
                  @click.stop="activateCard(card.resource_id)"
                >
                  {{ card.resource_id === activeCardId ? "展开完整内容" : "设为当前并展开" }}
                </button>
              </div>

              <div v-else class="space-y-5">
                <MarkdownContent
                  v-if="card.card_type === 'concept_map'"
                  :content="conceptMarkdown(card)"
                  :mermaid-source="conceptMermaidSource(card)"
                />

                <div v-else-if="card.card_type === 'code_snippet'" class="space-y-4">
                  <div class="rounded-[18px] border border-subtle bg-space-surface/55 p-4 shadow-card">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">
                      {{ codeLanguage(card).toUpperCase() }}
                    </p>
                    <pre class="mt-3 overflow-x-auto rounded-[16px] border border-subtle/80 bg-[#08111f] px-4 py-3 text-xs leading-6 text-slate-100">{{ fullCode(card) }}</pre>
                  </div>
                  <MarkdownContent
                    v-if="codeExplanation(card)"
                    :content="codeExplanation(card)"
                  />
                </div>

                <div v-else-if="card.card_type === 'interactive_exercise'" class="space-y-4">
                  <div class="rounded-[18px] border border-subtle bg-card p-4 shadow-card">
                    <p class="text-sm font-medium text-text-primary">{{ exercisePrompt(card) }}</p>
                    <div v-if="exerciseSteps(card).length" class="mt-4 space-y-3">
                      <div
                        v-for="(step, stepIndex) in exerciseSteps(card)"
                        :key="`${card.resource_id}-step-${stepIndex}`"
                        class="rounded-[16px] border border-subtle bg-space-surface/40 px-4 py-3"
                      >
                        <p class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">步骤 {{ stepIndex + 1 }}</p>
                        <p class="mt-2 text-sm leading-6 text-text-secondary">{{ step }}</p>
                      </div>
                    </div>
                  </div>

                  <div v-if="exerciseCheckpoints(card).length" class="rounded-[18px] border border-subtle bg-card p-4 shadow-card">
                    <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">检查点</p>
                    <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(checkpoint, checkpointIndex) in exerciseCheckpoints(card)" :key="`${card.resource_id}-checkpoint-${checkpointIndex}`">
                        {{ checkpoint }}
                      </li>
                    </ul>
                  </div>
                </div>

                <div v-else-if="card.card_type === 'video_summary'" class="space-y-4">
                  <div class="rounded-[18px] border border-subtle bg-card p-4 shadow-card">
                    <p class="text-sm leading-7 text-text-secondary">{{ videoSummary(card) }}</p>
                    <ul v-if="videoKeyPoints(card).length" class="mt-4 space-y-2 text-sm leading-6 text-text-secondary">
                      <li v-for="(point, pointIndex) in videoKeyPoints(card)" :key="`${card.resource_id}-point-${pointIndex}`">
                        {{ point }}
                      </li>
                    </ul>
                  </div>

                  <a
                    v-if="videoUrl(card)"
                    :href="videoUrl(card)"
                    target="_blank"
                    rel="noreferrer"
                    class="inline-flex rounded-full border border-secondary/25 bg-secondary-soft px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.10em] text-secondary transition-all duration-200 hover:border-secondary/35 hover:bg-secondary-soft/80"
                  >
                    打开视频链接
                  </a>
                </div>

                <div v-else-if="card.card_type === 'diagnostic_quiz'" class="space-y-4">
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
                      {{ diagnosticStatusText }}
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

                <MarkdownContent
                  v-else
                  :content="card.content"
                />
              </div>
            </template>
          </ResourceCard>
        </div>
      </div>

      <div class="mt-5 grid gap-3 xl:hidden">
        <div class="rounded-[20px] border border-subtle bg-card px-4 py-3 shadow-card">
          <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">推荐说明</p>
          <p class="mt-2 text-sm leading-6 text-text-muted">{{ recommendationDetail }}</p>
        </div>
        <div class="grid gap-3 sm:grid-cols-3">
          <div
            v-for="brief in learningBriefs"
            :key="`mobile-${brief.label}`"
            class="rounded-[20px] border border-subtle bg-card px-4 py-3 shadow-card"
          >
            <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">{{ brief.label }}</p>
            <p class="mt-2 text-lg font-black text-text-primary">{{ brief.value }}</p>
            <p class="mt-1 text-[11px] leading-5 text-text-muted">{{ brief.detail }}</p>
          </div>
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
import { extractCodePreview, extractTextPreview } from "../utils/markdownPreview.js";

const props = defineProps({
  cards: { type: Array, default: () => [] },
  currentNode: { type: String, default: "" },
  nodeTitle: { type: String, default: "" },
  pathNodes: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  overallProgress: { type: Number, default: 0 },
  masteredCount: { type: Number, default: 0 },
  lastDiagnostic: { type: Object, default: null },
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
const hydratedCardIds = ref([]);
const submittedScore = ref(null);

watch(
  () => props.cards,
  (cards) => {
    const nextIds = cards.map((card) => card.resource_id);
    orderedIds.value = nextIds;
    minimizedIds.value = [];
    activeCardId.value = nextIds[0] ?? "";
    hydratedCardIds.value = [];
    focusMode.value = false;
    answers.value = {};
    submittedScore.value = null;
  },
  { immediate: true },
);

const sortedCards = computed(() => {
  const orderIndex = new Map(orderedIds.value.map((id, index) => [id, index]));
  const latestByType = new Map();
  const extras = [];

  [...props.cards]
    .sort(
      (left, right) =>
        (orderIndex.get(left.resource_id) ?? Number.MAX_SAFE_INTEGER) -
        (orderIndex.get(right.resource_id) ?? Number.MAX_SAFE_INTEGER),
    )
    .forEach((card) => {
      if (["concept_map", "code_snippet", "interactive_exercise", "video_summary", "diagnostic_quiz"].includes(card.card_type)) {
        latestByType.set(card.card_type, card);
      } else {
        extras.push(card);
      }
    });

  const ordered = ["concept_map", "code_snippet", "interactive_exercise", "video_summary", "diagnostic_quiz"]
    .map((cardType) => latestByType.get(cardType))
    .filter(Boolean);

  return [...ordered, ...extras];
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
  sortedCards.value.find((card) => card.card_type === "diagnostic_quiz"),
);

const quizQuestions = computed(() => {
  const structuredQuestions = quizCard.value?.metadata?.questions;
  if (Array.isArray(structuredQuestions) && structuredQuestions.length) {
    return structuredQuestions.map((question) => ({
      id: question.id,
      prompt: question.prompt,
      options: question.options || [],
      answerIndex: question.answer_index ?? question.answerIndex ?? 0,
      explanation: question.explanation || "",
    }));
  }

  return props.buildQuiz(quizCard.value?.content ?? "").map((question) => ({
    id: question.id,
    prompt: question.prompt,
    options: question.options,
    answerIndex: question.answer ?? 0,
    explanation: "",
  }));
});
const allAnswered = computed(
  () => quizQuestions.value.length > 0 && quizQuestions.value.every((question) => answers.value[question.id] !== undefined),
);

const currentNodeMeta = computed(() =>
  props.pathNodes.find((node) => node.id === props.currentNode),
);

const currentMastery = computed(() =>
  Math.round((currentNodeMeta.value?.mastery ?? 0) * 100),
);

const availableTypes = computed(() => new Set(props.cards.map((card) => card.card_type)));
const nextPendingNode = computed(() =>
  props.pathNodes.find((node) => (node.mastery ?? 0) < 0.65 && node.id !== props.currentNode) ?? null,
);

const learningTone = computed(() => {
  if (props.loading) return "资源装配中";
  if (!props.cards.length) return "等待资源";
  if (currentMastery.value >= 65) return "节点达标";
  return "继续学习";
});

const recommendationTitle = computed(() => {
  if (props.loading) {
    return "正在同步当前节点的学习材料";
  }

  if (!props.cards.length) {
    return "优先装配本节点资源";
  }

  if (currentMastery.value < 65) {
    return "先完成本节点的概念理解与练习";
  }

  return nextPendingNode.value ? `准备进入下一节点：${nextPendingNode.value.title}` : "当前路径已进入收束阶段";
});

const recommendationDetail = computed(() => {
  if (props.loading) {
    return "保持当前节点不切换，系统会优先补齐概念、代码、练习与诊断四类材料。";
  }

  if (!props.cards.length) {
    return "从知识目录选择节点后，系统会根据当前学习状态自动生成对应学习矩阵。";
  }

  if (currentMastery.value < 65) {
    return "建议按“概念图 -> 代码示例 -> 互动练习 -> 诊断测评”的顺序推进，减少理解跳跃。";
  }

  return nextPendingNode.value
    ? "当前节点已接近达标，可以在完成本轮诊断后继续推进到下一个薄弱点。"
    : "路径中的主要薄弱点已经被覆盖，可以转入总结复盘或拓展练习。";
});

const learningBriefs = computed(() => [
  {
    label: "资源矩阵",
    value: `${props.cards.length}`,
    detail: props.cards.length ? "当前节点可用学习材料数" : "等待内容生成",
  },
  {
    label: "未达标节点",
    value: `${Math.max(props.pathNodes.length - props.masteredCount, 0)}`,
    detail: nextPendingNode.value ? `下一关注：${nextPendingNode.value.title}` : "当前暂无新的薄弱节点",
  },
  {
    label: "诊断状态",
    value: availableTypes.value.has("diagnostic_quiz") ? "已就绪" : "待生成",
    detail: availableTypes.value.has("diagnostic_quiz") ? "可以用测评确认掌握度" : "尚未生成诊断卡片",
  },
]);

const learningStages = computed(() => [
  {
    label: "目标",
    detail: currentNodeMeta.value ? "定位当前知识点" : "等待路径",
    active: Boolean(currentNodeMeta.value),
  },
  {
    label: "资源",
    detail: props.loading ? "生成中" : `${props.cards.length} 份材料`,
    active: props.loading || props.cards.length > 0,
  },
  {
    label: "练习",
    detail: availableTypes.value.has("interactive_exercise") ? "可训练" : "待生成",
    active: availableTypes.value.has("interactive_exercise"),
  },
  {
    label: "诊断",
    detail: availableTypes.value.has("diagnostic_quiz") ? "可提交" : "待评估",
    active: availableTypes.value.has("diagnostic_quiz"),
  },
]);

const diagnosticStatusText = computed(() => {
  if (props.lastDiagnostic) {
    const scorePercent = Math.round((props.lastDiagnostic.score ?? 0) * 100);
    const beforePercent = Math.round((props.lastDiagnostic.masteryBefore ?? 0) * 100);
    const afterPercent = Math.round((props.lastDiagnostic.masteryAfter ?? 0) * 100);
    if (props.lastDiagnostic.advancedToNextNode) {
      return `上次诊断得分 ${scorePercent}% · 掌握度 ${beforePercent}% -> ${afterPercent}% · 已推进到 ${props.lastDiagnostic.nextNodeTitle || "下一节点"}`;
    }
    return `上次诊断得分 ${scorePercent}% · 掌握度 ${beforePercent}% -> ${afterPercent}% · 继续停留当前节点`;
  }

  if (submittedScore.value !== null) {
    return `上次诊断得分 ${Math.round(submittedScore.value * 100)}%`;
  }

  return "请先回答所有题目，再提交诊断得分。";
});

function cardMetadata(card) {
  return card?.metadata || {};
}

function previewText(card) {
  const metadata = cardMetadata(card);
  if (card.card_type === "concept_map") {
    return metadata.summary || textPreview(card.content);
  }
  if (card.card_type === "interactive_exercise") {
    return metadata.prompt || textPreview(card.content);
  }
  if (card.card_type === "video_summary") {
    return metadata.summary || textPreview(card.content);
  }
  if (card.card_type === "diagnostic_quiz") {
    return quizQuestions.value[0]?.prompt || textPreview(card.content);
  }
  return textPreview(card.content);
}

function previewCode(card) {
  const metadata = cardMetadata(card);
  return metadata.code ? extractCodePreview(`\`\`\`\n${metadata.code}\n\`\`\``, 8) : codePreview(card.content);
}

function conceptMarkdown(card) {
  const metadata = cardMetadata(card);
  if (!metadata.title && !metadata.summary && !Array.isArray(metadata.bullets)) {
    return card.content;
  }

  const bullets = Array.isArray(metadata.bullets) && metadata.bullets.length
    ? `\n\n${metadata.bullets.map((bullet) => `- ${bullet}`).join("\n")}`
    : "";
  return `## ${metadata.title || cardLabel(card.card_type)}\n\n${metadata.summary || ""}${bullets}`.trim();
}

function conceptMermaidSource(card) {
  return cardMetadata(card).mermaid_source || "";
}

function codeLanguage(card) {
  return cardMetadata(card).language || "python";
}

function fullCode(card) {
  return cardMetadata(card).code || extractCodePreview(card.content, 40);
}

function codeExplanation(card) {
  return cardMetadata(card).explanation || "";
}

function exercisePrompt(card) {
  return cardMetadata(card).prompt || textPreview(card.content);
}

function exerciseSteps(card) {
  return Array.isArray(cardMetadata(card).steps) ? cardMetadata(card).steps : [];
}

function exerciseCheckpoints(card) {
  return Array.isArray(cardMetadata(card).checkpoints) ? cardMetadata(card).checkpoints : [];
}

function videoSummary(card) {
  return cardMetadata(card).summary || textPreview(card.content);
}

function videoKeyPoints(card) {
  return Array.isArray(cardMetadata(card).key_points) ? cardMetadata(card).key_points : [];
}

function videoUrl(card) {
  return cardMetadata(card).video_url || "";
}

watch(
  () => focusMode.value,
  (enabled) => {
    if (enabled && activeCardId.value) {
      hydrateCard(activeCardId.value);
    }
  },
);

watch(
  () => activeCardId.value,
  (cardId) => {
    if (focusMode.value && cardId) {
      hydrateCard(cardId);
    }
  },
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

function nodeChipClass(node) {
  if (node.id === props.currentNode) {
    return "border-secondary/40 bg-secondary-soft text-secondary shadow-[0_0_12px_var(--color-secondary-soft)]";
  }

  if (node.mastery >= 0.65) {
    return "border-success/25 text-success hover:border-success/40 hover:bg-success-soft";
  }

  if (nextPendingNode.value?.id === node.id) {
    return "border-primary/30 bg-primary-soft/80 text-primary hover:border-primary/45";
  }

  return "border-subtle text-text-muted hover:border-hover hover:text-text-secondary hover:bg-card-hover";
}

function isCardHydrated(cardId) {
  return hydratedCardIds.value.includes(cardId);
}

function hydrateCard(cardId) {
  if (!cardId || hydratedCardIds.value.includes(cardId)) {
    return;
  }

  hydratedCardIds.value = [...hydratedCardIds.value, cardId];
}

function activateCard(cardId) {
  if (!cardId) {
    return;
  }

  setActiveCard(cardId, true);
}

function setActiveCard(cardId, shouldHydrate = false) {
  if (!cardId) {
    return;
  }

  activeCardId.value = cardId;

  if (shouldHydrate) {
    hydrateCard(cardId);
  }
}

function textPreview(content) {
  return extractTextPreview(content, 190);
}

function codePreview(content) {
  return extractCodePreview(content, 8);
}

function previewLabel(cardType) {
  switch (cardType) {
    case "code_snippet":
      return "代码预览";
    case "interactive_exercise":
      return "练习预览";
    case "diagnostic_quiz":
      return "诊断预览";
    case "video_summary":
      return "摘要预览";
    case "concept_map":
    default:
      return "内容预览";
  }
}

function pinCard(cardId) {
  const next = orderedIds.value.filter((id) => id !== cardId);
  orderedIds.value = [cardId, ...next];
  setActiveCard(cardId);
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
  setActiveCard(cardId);
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
  setActiveCard(dragId.value);
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
    if (answers.value[question.id] === question.answerIndex) {
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
