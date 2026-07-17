<template>
  <section
    ref="scrollViewport"
    class="resource-canvas aurora-scroll relative h-full min-h-0 overflow-y-auto px-4 py-4 sm:px-5 lg:px-6"
    @wheel="forwardWheelToContent"
  >
    <header class="resource-canvas__header">
      <div class="resource-canvas__heading-row">
        <div class="min-w-0">
          <p class="resource-canvas__eyebrow">当前学习节点</p>
          <div class="resource-canvas__title-line">
            <h2>{{ nodeTitle || "等待装配" }}</h2>
            <span class="workspace-shell-chip workspace-shell-chip--accent shrink-0 px-3 py-1 text-[11px] font-semibold">
              {{ learningTone }}
            </span>
          </div>
        </div>

        <div class="resource-canvas__actions">
          <button
            type="button"
            class="workspace-shell-btn workspace-shell-btn--accent focus-ring px-3 py-2 text-[11px] font-semibold"
            @click="focusMode = !focusMode"
          >
            {{ focusMode ? "退出聚焦" : "聚焦模式" }}
          </button>
          <button
            type="button"
            class="workspace-shell-btn workspace-shell-btn--accent focus-ring px-3 py-2 text-[11px] font-semibold"
            :disabled="!currentNode || loading"
            @click="$emit('refresh')"
          >
            {{ loading ? "生成中..." : "刷新资源" }}
          </button>
        </div>
      </div>

      <div class="resource-canvas__status" aria-label="当前节点学习状态">
        <div class="resource-canvas__metric">
          <span>掌握度</span>
          <strong>{{ currentMastery }}%</strong>
        </div>
        <div class="resource-canvas__metric">
          <span>学习资料</span>
          <strong>{{ props.cards.length }} 份</strong>
        </div>
        <div class="resource-canvas__metric resource-canvas__metric--progress">
          <span>课程进度</span>
          <strong>{{ masteredCount }}/{{ pathNodes.length }}</strong>
        </div>
        <p class="resource-canvas__guidance">
          {{ currentNodeMeta ? resourceGuidance : "选择课程节点后，资料会在这里自动装配。" }}
        </p>
      </div>

      <div class="resource-canvas__nodes">
        <span class="resource-canvas__nodes-label">课程节点</span>
        <div ref="nodeScroller" class="aurora-scroll flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1">
        <button
          v-for="node in pathNodes"
          :key="node.id"
          :ref="(element) => setNodeButtonRef(node.id, element)"
          type="button"
          class="workspace-shell-chip focus-ring shrink-0 px-3.5 py-1.5 text-[11px] font-medium tracking-[0.06em] transition-all duration-200 active:scale-95"
          :class="nodeChipClass(node)"
          :aria-current="selectedNodeId === node.id ? 'step' : undefined"
          @click="selectNode(node.id)"
        >
          {{ node.title }}
        </button>
        </div>
      </div>

      <div class="resource-canvas__filters" aria-label="资源类型">
        <span class="resource-canvas__filters-label">资源类型</span>
        <div class="resource-canvas__filter-scroll aurora-scroll" role="group" aria-label="筛选学习资源">
          <button
            v-for="item in resourceFilterItems"
            :key="item.key"
            type="button"
            class="resource-canvas__filter focus-ring"
            :class="{ 'resource-canvas__filter--active': filterType === item.key }"
            :aria-pressed="String(filterType === item.key)"
            @click="emit('filter-change', item.key)"
          >
            <span>{{ item.label }}</span>
            <span class="resource-canvas__filter-count" aria-hidden="true">{{ item.count }}</span>
          </button>
        </div>
      </div>
    </header>

    <div class="relative pb-4">
        <div v-if="!cards.length && !loading" class="flex h-full min-h-[420px] items-center justify-center">
        <div class="flex max-w-[44ch] flex-col items-center text-center animate-fadeIn">
          <div class="mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-primary-soft">
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

      <!-- 全部：原始卡片网格 -->
      <div v-if="filterType === 'all'" class="resource-canvas__grid resource-canvas__grid--multiple" :key="'grid-all'">
        <template v-for="(slot, index) in cardTypeSlots" :key="'card-'+filterType+'-'+slot.type">
          <div
            v-if="slot.card && !minimizedIds.includes(slot.card.resource_id)"
            :draggable="true"
            class="resource-canvas__slot animate-cardIn h-full card-depth transition-all duration-300"
            :style="{ animationDelay: `${index * 120}ms` }"
            @dragstart="onDragStart(slot.card.resource_id)"
            @dragover.prevent
            @drop="onDrop(slot.card.resource_id)"
          >
            <!-- 统一卡片模板 -->
            <div class="h-full flex flex-col rounded-[20px] border border-subtle bg-card overflow-hidden shadow-sm transition-all duration-300 hover:-translate-y-1.5 hover:shadow-md hover:border-primary/30 cursor-pointer">
              <div class="h-1 shrink-0" :style="{ background: slot.color }" />
              <div class="flex flex-col flex-1 p-5 min-h-0">
              <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted shrink-0">{{ slot.label }}</p>
              <div class="flex-[2] min-h-0 mt-2 overflow-hidden">
                <pre v-if="slot.card && resourceType(slot.card) === 'code_snippet'" class="rounded-lg border border-subtle bg-[#0d1117] px-4 py-3 text-xs leading-6 text-slate-100 line-clamp-4 h-full">{{ previewCode(slot.card) }}</pre>
                <p v-else-if="slot.card" class="text-sm leading-7 text-text-secondary line-clamp-[8]">{{ previewText(slot.card) }}</p>
                <p v-else class="text-sm leading-7 text-text-muted">点击生成按钮来创建此资源</p>
              </div>
              <div class="flex-[1] flex flex-col justify-center shrink-0 mt-2">
                <p class="text-[11px] text-text-muted mb-2">{{ previewDesc(slot.type) }}</p>
                <button type="button" class="workspace-shell-btn workspace-shell-btn--accent focus-ring w-full px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.10em] mb-2" @click.stop="slot.card && openCard(slot.card)">打开完整内容</button>
                <p class="text-[10px] text-text-muted/60 text-center italic">{{ slotSlogan(slot.type) }}</p>
              </div>
              </div>
            </div>
          </div>
          <div v-else class="resource-canvas__slot animate-cardIn h-full transition-all duration-300" :style="{ animationDelay: `${index * 40}ms` }">
            <div class="slot-empty group h-full rounded-xl border border-dashed border-subtle bg-card flex flex-col items-center justify-center gap-4 p-6" :style="{ '--rail-accent': slot.color }">
              <span class="slot-empty-icon text-[2.25rem]" :style="{ animationDelay: `${index * 0.4}s` }" aria-hidden="true">{{ slot.icon }}</span>
              <div class="text-center space-y-0.5"><p class="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-text-muted">{{ slot.label }}</p><p class="text-[11px] text-text-secondary">尚未生成</p></div>
              <button v-if="currentNode" type="button" class="btn-ripple workspace-shell-btn workspace-shell-btn--accent focus-ring px-4 py-2 text-[11px] font-semibold tracking-[0.06em]" @click="$emit('generate-card', { nodeId: currentNode, cardType: slot.type })">生成</button>
            </div>
          </div>
        </template>
      </div>

      <!-- 单类型：大页面式 -->
      <div v-else class="space-y-6" :key="'page-'+filterType">
        <template v-for="slot in cardTypeSlots" :key="slot.type">
          <div v-if="slot.card && !minimizedIds.includes(slot.card.resource_id)" class="rounded-xl border border-subtle bg-card p-6">
            <template v-for="card of [slot.card]" :key="slot.type">
              <div class="flex items-center gap-3 mb-5">
                <span class="text-xs font-semibold text-text-muted">{{ slot.label }}</span>
                <span class="h-px flex-1 bg-subtle" />
              </div>
              <article v-if="resourceType(card) === 'concept_map'" class="text-sm leading-7 text-text-secondary">
                <div class="rounded-lg border-l-2 border-primary pl-4 py-1 mb-8">
                  <p class="text-text-primary font-medium">{{ conceptSummary(card) }}</p>
                </div>
                <template v-if="conceptSections(card).length">
                  <section v-for="(section, index) in conceptSections(card)" :key="'sec-'+index" class="mt-8 first:mt-0">
                    <h3 class="text-base font-semibold text-text-primary">{{ section.heading }}</h3>
                    <p class="mt-2 border-l border-subtle pl-4">{{ section.body }}</p>
                  </section>
                </template>
                <ul v-if="conceptObjectives(card).length" class="mt-8 rounded-lg bg-[#FAFCFB] py-3 px-4 space-y-2"><li v-for="(item, index) in conceptObjectives(card)" :key="'obj-'+index" class="flex gap-2"><span class="text-primary font-medium shrink-0 text-xs">{{ index + 1 }}.</span><span>{{ item }}</span></li></ul>
                <ul v-if="conceptBullets(card).length" class="mt-8 space-y-2 pl-1"><li v-for="item in conceptBullets(card)" :key="'b-'+item" class="flex gap-2"><span class="text-text-muted shrink-0">&bull;</span><span>{{ item }}</span></li></ul>
                <MarkdownContent v-if="conceptMermaidSource(card)" class="mt-8" :content="''" :mermaid-source="conceptMermaidSource(card)" />
                <div v-if="conceptMisconceptions(card).length" class="mt-8 rounded-lg border border-warning-soft bg-warning-soft/30 py-3 px-4 space-y-1.5"><p class="text-xs font-semibold text-warning-dark mb-2">常见误区</p><ul class="space-y-1.5"><li v-for="item in conceptMisconceptions(card)" :key="'mis-'+item" class="text-xs flex gap-2"><span class="text-warning shrink-0">&times;</span><span>{{ item }}</span></li></ul></div>
                <ul v-if="conceptReviewPrompts(card).length" class="mt-8 space-y-2 bg-[#FAFCFB] rounded-lg py-3 px-4"><li v-for="(item, index) in conceptReviewPrompts(card)" :key="'rev-'+index" class="flex gap-2"><span class="text-primary font-medium shrink-0 text-xs">{{ index + 1 }}.</span><span>{{ item }}</span></li></ul>
              </article>
              <article v-else-if="resourceType(card) === 'code_snippet'" class="text-sm leading-7 text-text-secondary">
                <div class="rounded-lg border-l-2 border-primary pl-4 py-1 mb-8">
                  <p>{{ codeScenario(card) }}</p>
                </div>
                <ul v-if="codePrerequisites(card).length" class="flex flex-wrap gap-1.5 mb-8"><li v-for="item in codePrerequisites(card)" :key="'pre-'+item" class="rounded-full border border-subtle px-3 py-0.5 text-xs text-text-muted">{{ item }}</li></ul>
                <div class="overflow-hidden rounded-lg border border-subtle bg-[#0d1117] mb-8"><div class="px-4 py-2 border-b border-white/5"><span class="text-xs text-slate-400">{{ codeLanguage(card) }}</span></div><pre class="overflow-x-auto p-4 text-[13px] leading-6 text-slate-100"><code>{{ fullCode(card) }}</code></pre></div>
                <MarkdownContent v-if="codeExplanation(card)" class="mb-8" :content="codeExplanation(card)" />
                <ol v-if="codeWalkthrough(card).length" class="mb-8 space-y-3 bg-[#FAFCFB] rounded-lg py-3 px-4"><li v-for="(item, index) in codeWalkthrough(card)" :key="'walk-'+index" class="flex gap-3"><span class="text-primary font-medium shrink-0 text-xs w-5">{{ index + 1 }}</span><span>{{ item }}</span></li></ol>
                <ul v-if="codeComplexityNotes(card).length" class="mb-8 space-y-2"><li v-for="item in codeComplexityNotes(card)" :key="'cx-'+item" class="flex gap-2"><span class="text-text-muted shrink-0">&bull;</span><span>{{ item }}</span></li></ul>
                <div v-if="codePitfalls(card).length" class="mb-8 rounded-lg border border-warning-soft bg-warning-soft/30 py-3 px-4 space-y-1.5"><p class="text-xs font-semibold text-warning-dark mb-2">常见坑点</p><ul class="space-y-1.5"><li v-for="item in codePitfalls(card)" :key="'pit-'+item" class="text-xs flex gap-2"><span class="text-warning shrink-0">!</span><span>{{ item }}</span></li></ul></div>
                <ul v-if="codeExperiments(card).length" class="space-y-2"><li v-for="item in codeExperiments(card)" :key="'exp-'+item" class="flex gap-2"><span class="text-text-muted shrink-0">&bull;</span><span>{{ item }}</span></li></ul>
              </article>
              <article v-else-if="resourceType(card) === 'interactive_exercise'" class="text-sm leading-7 text-text-secondary">
                <div class="rounded-lg border-l-2 border-primary pl-4 py-1 mb-8">
                  <p class="text-text-primary font-medium">{{ exerciseGoal(card) }}</p>
                  <p class="mt-2">{{ exercisePrompt(card) }}</p>
                </div>
                <ol v-if="exerciseSteps(card).length" class="mb-8 space-y-3 bg-[#FAFCFB] rounded-lg py-3 px-4"><li v-for="(step, stepIndex) in exerciseSteps(card)" :key="'step-'+stepIndex" class="flex gap-3"><span class="text-primary font-semibold shrink-0 text-xs w-5 pt-0.5">{{ stepIndex + 1 }}</span><span>{{ step }}</span></li></ol>
                <ul v-if="exerciseCheckpoints(card).length" class="mb-8 space-y-2"><li v-for="item in exerciseCheckpoints(card)" :key="'cp-'+item" class="flex gap-2"><span class="text-success shrink-0">&check;</span><span>{{ item }}</span></li></ul>
                <div v-if="exerciseHints(card).length" class="mb-8 rounded-lg border border-info-soft bg-info-soft/20 py-3 px-4 space-y-1.5"><p class="text-xs font-semibold text-info-dark mb-2">提示</p><ul class="space-y-1.5"><li v-for="(hint, index) in exerciseHints(card)" :key="'hint-'+index" class="text-xs flex gap-2"><span class="text-info shrink-0">{{ index + 1 }}.</span><span>{{ hint }}</span></li></ul></div>
                <div v-if="exerciseExpectedOutcome(card) || exerciseSolutionOutline(card)" class="grid gap-8 sm:grid-cols-2"><div v-if="exerciseExpectedOutcome(card)" class="rounded-lg bg-[#FAFCFB] py-3 px-4"><h4 class="text-xs font-semibold text-text-muted mb-2">预期结果</h4><p>{{ exerciseExpectedOutcome(card) }}</p></div><div v-if="exerciseSolutionOutline(card)" class="rounded-lg bg-[#FAFCFB] py-3 px-4"><h4 class="text-xs font-semibold text-text-muted mb-2">参考思路</h4><p>{{ exerciseSolutionOutline(card) }}</p></div></div>
              </article>
              <article v-else-if="resourceType(card) === 'video_summary'" class="text-sm leading-7 text-text-secondary">
                <p>{{ videoSummary(card) }}</p>
                <ul v-if="videoKeyPoints(card).length" class="mt-10 space-y-2"><li v-for="point in videoKeyPoints(card)" :key="'kp-'+point">{{ point }}</li></ul>
                <div v-if="videoTimeline(card).length" class="mt-10 space-y-4"><div v-for="item in videoTimeline(card)" :key="'tl-'+item.label"><span class="text-xs font-medium text-text-muted">{{ item.label }}</span><p class="mt-1">{{ item.summary }}</p></div></div>
                <div v-if="videoWatchFocus(card).length || videoReviewQuestions(card).length" class="mt-10 grid gap-8 sm:grid-cols-2"><ul v-if="videoWatchFocus(card).length" class="space-y-2"><li v-for="item in videoWatchFocus(card)" :key="'wf-'+item">{{ item }}</li></ul><ul v-if="videoReviewQuestions(card).length" class="space-y-2"><li v-for="(item, index) in videoReviewQuestions(card)" :key="'rq-'+index">{{ index + 1 }}. {{ item }}</li></ul></div>
                <a v-if="videoUrl(card)" :href="videoUrl(card)" target="_blank" rel="noreferrer" class="inline-block mt-10 text-xs font-medium text-primary hover:underline">打开视频链接 &rarr;</a>
              </article>
              <article v-else-if="resourceType(card) === 'diagnostic_quiz'" class="text-sm leading-7 text-text-secondary">
                <p v-if="quizGuidance(card)" class="text-text-muted">{{ quizGuidance(card) }}</p>
                <div v-for="question in quizQuestions" :key="question.id" class="mt-10"><p class="font-medium text-text-primary">{{ question.prompt }}</p><p v-if="question.skillTag || question.difficulty" class="mt-1 text-xs text-text-muted">{{ [question.skillTag, question.difficulty].filter(Boolean).join(" · ") }}</p><div class="mt-4 space-y-2"><button v-for="(option, optionIndex) in question.options" :key="`${question.id}-${optionIndex}`" type="button" class="focus-ring w-full rounded-lg border px-4 py-2.5 text-left text-sm transition-colors" :class="answerClass(question.id, optionIndex)" @click="setAnswer(question.id, optionIndex)">{{ option }}</button></div><div v-if="submittedScore !== null && question.explanation" class="mt-4 text-xs text-text-muted">{{ question.explanation }}</div></div>
                <div class="mt-10 flex flex-wrap items-center justify-between gap-3"><p class="text-xs text-text-muted">{{ diagnosticStatusText }}</p><button type="button" class="focus-ring btn-capsule" :disabled="!allAnswered || loading" @click="submitQuizScore">提交诊断</button></div>
                <p v-if="quizAfterGuidance(card) && submittedScore !== null" class="mt-8">{{ quizAfterGuidance(card) }}</p>
              </article>
              <MarkdownContent v-else :content="bodyMarkdown(card)" />
            </template>
          </div>
          <div v-else class="rounded-xl border border-dashed border-subtle/30 p-8 flex flex-col items-center justify-center gap-3">
            <span class="text-3xl opacity-60" aria-hidden="true">{{ slot.icon }}</span>
            <p class="text-xs text-text-muted">{{ slot.label }} · 尚未生成</p>
            <button v-if="currentNode" type="button" class="focus-ring rounded-lg border border-subtle px-4 py-2 text-xs text-text-muted hover:text-text-primary hover:border-primary/30 transition-colors" @click="$emit('generate-card', { nodeId: currentNode, cardType: slot.type })">生成</button>
          </div>
        </template>
      </div>

    </div>

    <footer v-if="minimizedCards.length" class="pt-5">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">已最小化</span>
        <button
          v-for="card in minimizedCards"
          :key="card.resource_id"
          type="button"
          class="workspace-shell-btn focus-ring px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.10em]"
          @click="restoreCard(card.resource_id)"
        >
          {{ cardLabel(resourceType(card)) }}
        </button>
      </div>
    </footer>
  </section>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";
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
  filterType: { type: String, default: "all" },
  getCardLabel: { type: Function, required: true },
  getAgentLabel: { type: Function, required: true },
  buildQuiz: { type: Function, required: true },
});

const emit = defineEmits(["submit-quiz", "select-node", "refresh", "generate-card", "filter-change"]);

const orderedIds = ref([]);
const minimizedIds = ref([]);
const activeCardId = ref("");
const dragId = ref("");
const focusMode = ref(false);
const answers = ref({});
const submittedScore = ref(null);
const quizAttemptNumber = ref(1);
const quizStartedAt = ref(Date.now());
const quizEventId = ref("");
const scrollViewport = ref(null);
const nodeScroller = ref(null);
const nodeButtonRefs = new Map();
const selectedNodeId = ref(props.currentNode);

watch(
  [() => props.currentNode, () => props.loading, () => props.pathNodes.length],
  async ([nodeId, loading]) => {
    if (nodeId) {
      selectedNodeId.value = nodeId;
    }

    if (loading || !nodeId) {
      return;
    }

    await nextTick();
    alignNodeToLeft(nodeId);
  },
  { immediate: true, flush: "post" },
);

// ── 5-type slot system ─────────────────────────────────────────────────
const CARD_TYPES = [
  { type: "concept_map",          label: "概念导图", filterLabel: "概念", icon: "🗺", sidebarKey: "concept",  color: "var(--learning-concept)" },
  { type: "code_snippet",         label: "代码示例", filterLabel: "代码", icon: "💻", sidebarKey: "code",     color: "var(--learning-code)" },
  { type: "interactive_exercise", label: "互动练习", filterLabel: "练习", icon: "✏️", sidebarKey: "practice", color: "var(--learning-practice)" },
  { type: "video_summary",        label: "视频摘要", filterLabel: "视频", icon: "🎬", sidebarKey: "video",    color: "var(--learning-video)" },
  { type: "diagnostic_quiz",      label: "诊断测验", filterLabel: "测验", icon: "📋", sidebarKey: "quiz",     color: "var(--learning-quiz)" },
];

const resourceFilterItems = computed(() => [
  { key: "all", label: "全部", count: props.cards.length },
  ...CARD_TYPES.map((item) => ({
    key: item.sidebarKey,
    label: item.filterLabel,
    count: props.cards.filter((card) => resourceType(card) === item.type).length,
  })),
]);

/** Map card_type → latest card */
const cardsByType = computed(() => {
  const map = {};
  for (const card of props.cards) {
    const t = resourceType(card);
    if (t) map[t] = card;
  }
  return map;
});

/**
 * Visible slots after applying filterType.
 * "all" → all 5 types; otherwise only the matching type.
 */
const cardTypeSlots = computed(() => {
  let filtered = props.filterType && props.filterType !== "all"
    ? CARD_TYPES.filter((m) => m.sidebarKey === props.filterType)
    : CARD_TYPES;

  if (focusMode.value && activeCardId.value) {
    const activeType = resourceType(props.cards.find((card) => card.resource_id === activeCardId.value));
    filtered = filtered.filter((meta) => meta.type === activeType);
  }

  return filtered.map((meta) => ({
    ...meta,
    card: cardsByType.value[meta.type] ?? null,
  }));
});

const singleCardId = computed(() => {
  if (cardTypeSlots.value.length !== 1) {
    return "";
  }

  const cardId = cardTypeSlots.value[0].card?.resource_id ?? "";
  return minimizedIds.value.includes(cardId) ? "" : cardId;
});

const isSingleCardView = computed(() => Boolean(singleCardId.value));

watch(
  () => props.filterType,
  () => {
    focusMode.value = false;
  },
);

watch(
  () => props.cards,
  (cards) => {
    const nextIds = cards.map((card) => card.resource_id);
    orderedIds.value = nextIds;
    minimizedIds.value = [];
    activeCardId.value = nextIds[0] ?? "";
    focusMode.value = false;
  },
  { immediate: true },
);

watch(
  singleCardId,
  (cardId) => {
    if (cardId) {
      setActiveCard(cardId);
    }
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
      if (["concept_map", "code_snippet", "interactive_exercise", "video_summary", "diagnostic_quiz"].includes(resourceType(card))) {
        latestByType.set(resourceType(card), card);
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
  sortedCards.value.find((card) => resourceType(card) === "diagnostic_quiz"),
);

watch(
  [() => props.currentNode, () => quizCard.value?.resource_id ?? quizCard.value?.id ?? ""],
  () => {
    answers.value = {};
    submittedScore.value = null;
    quizAttemptNumber.value = 1;
    quizStartedAt.value = Date.now();
    quizEventId.value = "";
  },
);

const quizQuestions = computed(() => {
  const structuredQuestions = structuredPayload(quizCard.value)?.questions;
  if (Array.isArray(structuredQuestions) && structuredQuestions.length) {
    return structuredQuestions.map((question) => ({
      id: question.id,
      prompt: question.prompt,
      options: question.options || [],
      answerIndex: question.answer_index ?? question.answerIndex ?? 0,
      explanation: question.explanation || "",
      skillTag: question.skill_tag || "",
      difficulty: question.difficulty || "",
    }));
  }

  return props.buildQuiz(bodyMarkdown(quizCard.value)).map((question) => ({
    id: question.id,
    prompt: question.prompt,
    options: question.options,
    answerIndex: question.answer ?? 0,
    explanation: "",
    skillTag: "",
    difficulty: "",
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

const resourceGuidance = computed(() => ({
  concept: "概念导图帮助你建立当前知识点的整体结构。",
  code: "代码示例帮助你理解知识点如何落到实际实现。",
  practice: "互动练习帮助你通过应用与反思巩固理解。",
  video: "视频摘要帮助你快速回顾当前知识点的核心内容。",
  quiz: "诊断测验用于检验掌握程度并发现薄弱环节。",
  all: "多种学习资源共同支持理解、实践与诊断的完整过程。",
}[props.filterType] ?? "当前资源帮助你理解并掌握这个知识点。"));

const availableTypes = computed(() => new Set(props.cards.map((card) => resourceType(card))));
const nextPendingNode = computed(() =>
  props.pathNodes.find((node) => (node.mastery ?? 0) < 0.65 && node.id !== props.currentNode) ?? null,
);

const learningTone = computed(() => {
  if (props.loading) return "资源装配中";
  if (!props.cards.length) return "等待资源";
  if (currentMastery.value >= 65) return "节点达标";
  return "继续学习";
});

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

function resourceType(card) {
  return card?.resource_type || card?.card_type || card?.type || "";
}

function bodyMarkdown(card) {
  return card?.body_markdown || card?.content || "";
}

function structuredPayload(card) {
  return card?.structured_payload || card?.metadata || {};
}
function cardMetadata(card) {
  return structuredPayload(card);
}

function previewText(card) {
  const metadata = cardMetadata(card);
  if (resourceType(card) === "concept_map") {
    return metadata.summary || textPreview(bodyMarkdown(card));
  }
  if (resourceType(card) === "interactive_exercise") {
    return metadata.prompt || textPreview(bodyMarkdown(card));
  }
  if (resourceType(card) === "video_summary") {
    return metadata.summary || textPreview(bodyMarkdown(card));
  }
  if (resourceType(card) === "diagnostic_quiz") {
    return quizQuestions.value[0]?.prompt || textPreview(bodyMarkdown(card));
  }
  return textPreview(bodyMarkdown(card));
}

function previewCode(card) {
  const metadata = cardMetadata(card);
  return metadata.code ? extractCodePreview(`\`\`\`\n${metadata.code}\n\`\`\``, 8) : codePreview(bodyMarkdown(card));
}

function conceptMarkdown(card) {
  const metadata = cardMetadata(card);
  if (!metadata.title && !metadata.summary && !Array.isArray(metadata.bullets)) {
    return bodyMarkdown(card);
  }

  const sections = Array.isArray(metadata.sections)
    ? `\n\n${metadata.sections.map((section) => `### ${section.heading}\n${section.body}`).join("\n\n")}`
    : "";
  const bullets = Array.isArray(metadata.bullets) && metadata.bullets.length
    ? `\n\n${metadata.bullets.map((bullet) => `- ${bullet}`).join("\n")}`
    : "";
  return `## ${metadata.title || cardLabel(resourceType(card))}\n\n${metadata.summary || ""}${sections}${bullets}`.trim();
}

function conceptMermaidSource(card) {
  return cardMetadata(card).mermaid_source || "";
}

function conceptSummary(card) {
  return cardMetadata(card).summary || textPreview(bodyMarkdown(card));
}

function conceptObjectives(card) {
  return Array.isArray(cardMetadata(card).learning_objectives) ? cardMetadata(card).learning_objectives : [];
}

function conceptSections(card) {
  return Array.isArray(cardMetadata(card).sections) ? cardMetadata(card).sections : [];
}

function conceptBullets(card) {
  return Array.isArray(cardMetadata(card).bullets) ? cardMetadata(card).bullets : [];
}

function conceptMisconceptions(card) {
  return Array.isArray(cardMetadata(card).common_misconceptions) ? cardMetadata(card).common_misconceptions : [];
}

function conceptReviewPrompts(card) {
  return Array.isArray(cardMetadata(card).review_prompts) ? cardMetadata(card).review_prompts : [];
}

function codeLanguage(card) {
  return cardMetadata(card).language || "python";
}

function fullCode(card) {
  return cardMetadata(card).code || extractCodePreview(bodyMarkdown(card), 40);
}

function codeExplanation(card) {
  return cardMetadata(card).explanation || "";
}

function codeScenario(card) {
  return cardMetadata(card).scenario || codeExplanation(card) || textPreview(bodyMarkdown(card));
}

function codePrerequisites(card) {
  return Array.isArray(cardMetadata(card).prerequisites) ? cardMetadata(card).prerequisites : [];
}

function codeWalkthrough(card) {
  return Array.isArray(cardMetadata(card).walkthrough_steps) ? cardMetadata(card).walkthrough_steps : [];
}

function codeComplexityNotes(card) {
  return Array.isArray(cardMetadata(card).complexity_notes) ? cardMetadata(card).complexity_notes : [];
}

function codePitfalls(card) {
  return Array.isArray(cardMetadata(card).pitfalls) ? cardMetadata(card).pitfalls : [];
}

function codeExperiments(card) {
  return Array.isArray(cardMetadata(card).experiments) ? cardMetadata(card).experiments : [];
}

function exercisePrompt(card) {
  return cardMetadata(card).prompt || textPreview(bodyMarkdown(card));
}

function exerciseGoal(card) {
  return cardMetadata(card).goal || exercisePrompt(card);
}

function exerciseSteps(card) {
  return Array.isArray(cardMetadata(card).steps) ? cardMetadata(card).steps : [];
}

function exerciseCheckpoints(card) {
  return Array.isArray(cardMetadata(card).checkpoints) ? cardMetadata(card).checkpoints : [];
}

function exerciseHints(card) {
  return Array.isArray(cardMetadata(card).hints) ? cardMetadata(card).hints : [];
}

function exerciseExpectedOutcome(card) {
  return cardMetadata(card).expected_outcome || "";
}

function exerciseSolutionOutline(card) {
  return cardMetadata(card).solution_outline || "";
}

function videoSummary(card) {
  return cardMetadata(card).summary || textPreview(bodyMarkdown(card));
}

function videoKeyPoints(card) {
  return Array.isArray(cardMetadata(card).key_points) ? cardMetadata(card).key_points : [];
}

function videoUrl(card) {
  return cardMetadata(card).video_url || "";
}

function videoTimeline(card) {
  return Array.isArray(cardMetadata(card).timeline) ? cardMetadata(card).timeline : [];
}

function videoWatchFocus(card) {
  return Array.isArray(cardMetadata(card).watch_focus) ? cardMetadata(card).watch_focus : [];
}

function videoReviewQuestions(card) {
  return Array.isArray(cardMetadata(card).review_questions) ? cardMetadata(card).review_questions : [];
}

function quizGuidance(card) {
  return cardMetadata(card).summary || "请先独立判断考查点，再结合当前节点材料选择答案。";
}

function quizAfterGuidance(card) {
  return cardMetadata(card).after_quiz_guidance || "";
}

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

function nodeChipClass(node) {
  if (node.id === selectedNodeId.value) {
    return "border-primary/45 bg-primary-soft font-semibold text-primary-dark ring-1 ring-primary/20";
  }

  if (node.mastery >= 0.65) {
    return "border-success/25 text-success hover:border-success/40 hover:bg-success-soft";
  }

  if (nextPendingNode.value?.id === node.id) {
    return "border-primary/30 bg-primary-soft/80 text-primary hover:border-primary/45";
  }

  return "border-subtle text-text-muted hover:border-hover hover:text-text-secondary hover:bg-card-hover";
}

function setNodeButtonRef(nodeId, element) {
  if (element instanceof HTMLElement) {
    nodeButtonRefs.set(nodeId, element);
    return;
  }

  nodeButtonRefs.delete(nodeId);
}

function selectNode(nodeId) {
  selectedNodeId.value = nodeId;
  emit("select-node", nodeId);
}

function alignNodeToLeft(nodeId) {
  const scroller = nodeScroller.value;
  const button = nodeButtonRefs.get(nodeId);
  if (!(scroller instanceof HTMLElement) || !(button instanceof HTMLElement)) {
    return;
  }

  const scrollerRect = scroller.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const targetLeft = Math.max(0, scroller.scrollLeft + buttonRect.left - scrollerRect.left);
  const workspace = scroller.closest(".workspace-shell");
  const reduceMotion = workspace?.classList.contains("is-reduced-motion")
    || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  scroller.scrollTo({
    left: targetLeft,
    behavior: reduceMotion ? "auto" : "smooth",
  });
}

function activateCard(cardId) {
  if (!cardId) {
    return;
  }

  setActiveCard(cardId);
}

function openCard(card) {
  if (!card?.resource_id) {
    return;
  }

  setActiveCard(card.resource_id);
  if (isSingleCardView.value) {
    return;
  }

  const filterKey = CARD_TYPES.find((item) => item.type === resourceType(card))?.sidebarKey;
  if (filterKey) {
    emit("filter-change", filterKey);
    return;
  }

  activateCard(card.resource_id);
}

function setActiveCard(cardId) {
  if (!cardId) {
    return;
  }

  activeCardId.value = cardId;
}

function textPreview(content) {
  return extractTextPreview(content, 190);
}

function codePreview(content) {
  return extractCodePreview(content, 8);
}

function previewLabel(cardType) {
  switch (cardType) {
    case "code_snippet": return "代码示例";
    case "interactive_exercise": return "互动练习";
    case "diagnostic_quiz": return "诊断测验";
    case "video_summary": return "视频摘要";
    case "concept_map":
    default: return "概念导图";
  }
}

function previewDesc(cardType) {
  switch (cardType) {
    case "code_snippet": return "可运行的代码片段与逐步讲解";
    case "interactive_exercise": return "动手练习，巩固当前知识点";
    case "diagnostic_quiz": return "检测掌握程度，定位薄弱环节";
    case "video_summary": return "视频摘要，快速回顾核心内容";
    case "concept_map":
    default: return "结构化知识框架与学习要点";
  }
}

const SLOGANS = [
  "学而不思则罔，思而不学则殆",
  "温故而知新，可以为师矣",
  "知之者不如好之者，好之者不如乐之者",
  "千里之行，始于足下",
  "不积跬步，无以至千里",
  "锲而不舍，金石可镂",
  "工欲善其事，必先利其器",
  "博观而约取，厚积而薄发",
  "纸上得来终觉浅，绝知此事要躬行",
  "书山有路勤为径，学海无涯苦作舟",
  "敏而好学，不耻下问",
  "三人行，必有我师焉",
  "学如逆水行舟，不进则退",
  "业精于勤，荒于嬉",
  "读书破万卷，下笔如有神",
  "问渠那得清如许，为有源头活水来",
  "非学无以广才，非志无以成学",
  "路漫漫其修远兮，吾将上下而求索",
  "少壮不努力，老大徒伤悲",
  "黑发不知勤学早，白首方悔读书迟",
];

let _sloganIdx = 0;
function slotSlogan(_cardType) {
  const s = SLOGANS[_sloganIdx % SLOGANS.length];
  _sloganIdx++;
  return s;
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
  const resourceId = quizCard.value?.resource_id ?? quizCard.value?.id;
  if (!resourceId) return;
  if (!quizEventId.value) {
    quizEventId.value = `diagnostic-${resourceId}-${quizAttemptNumber.value}-${Date.now()}`;
  }
  submittedScore.value = score;
  emit("submit-quiz", {
    eventId: quizEventId.value,
    resourceId: String(resourceId),
    durationMs: Math.max(0, Date.now() - quizStartedAt.value),
    attemptNumber: quizAttemptNumber.value,
    usedHint: false,
    answers: quizQuestions.value.map((question) => ({
      questionId: question.id,
      selectedOptionIndex: answers.value[question.id],
    })),
    onRecorded() {
      quizAttemptNumber.value += 1;
      quizEventId.value = "";
    },
    onFailure() {
      submittedScore.value = null;
    },
  });
}

function forwardWheelToContent(event) {
  if (!(scrollViewport.value instanceof HTMLElement)) {
    return;
  }

  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  if (scrollViewport.value.contains(target)) {
    return;
  }

  if (target.closest("textarea, input, select, [contenteditable='true']")) {
    return;
  }

  scrollViewport.value.scrollTop += event.deltaY;
}
</script>

<style scoped>
.resource-canvas {
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--space-elevated) 62%, transparent), transparent 22rem);
  overscroll-behavior: contain;
}

.resource-canvas__grid {
  display: grid;
  width: 100%;
  gap: 1rem;
}

.resource-canvas__grid--single {
  grid-template-columns: minmax(0, 1fr);
}

.resource-canvas__grid--single .resource-canvas__slot {
  min-height: max(36rem, calc(100dvh - 18rem));
}

.resource-canvas__grid--multiple {
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 19rem), 1fr));
  grid-auto-rows: 30rem;
}

.resource-canvas__slot {
  min-width: 0;
}

.resource-canvas__header {
  display: grid;
  gap: 0.75rem;
  padding-bottom: 1rem;
}

.resource-canvas__heading-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.resource-canvas__eyebrow,
.resource-canvas__nodes-label,
.resource-canvas__metric span {
  color: var(--text-muted);
  font-size: 0.7rem;
  font-weight: 800;
  line-height: 1.2;
}

.resource-canvas__title-line {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.3rem;
}

.resource-canvas__title-line h2 {
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 1.35rem;
  font-weight: 850;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-canvas__actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 0.5rem;
}

.resource-canvas__status {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0;
  border-block: 1px solid var(--border-subtle);
  padding: 0.55rem 0;
}

.resource-canvas__metric {
  display: flex;
  flex-shrink: 0;
  align-items: baseline;
  gap: 0.4rem;
  padding: 0 0.85rem;
  border-right: 1px solid var(--border-subtle);
}

.resource-canvas__metric:first-child {
  padding-left: 0;
}

.resource-canvas__metric strong {
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

.resource-canvas__guidance {
  min-width: 0;
  overflow: hidden;
  margin-left: 0.85rem;
  color: var(--text-secondary);
  font-size: 0.78rem;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-canvas__nodes {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.75rem;
}

.resource-canvas__nodes-label {
  flex-shrink: 0;
}

.resource-canvas__filters {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.75rem;
  padding-top: 0.15rem;
}

.resource-canvas__filters-label {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 0.7rem;
  font-weight: 800;
  line-height: 1.2;
}

.resource-canvas__filter-scroll {
  display: flex;
  min-width: 0;
  flex: 1;
  gap: 0.35rem;
  overflow-x: auto;
  padding: 0.15rem;
}

.resource-canvas__filter {
  display: inline-flex;
  min-height: 2.75rem;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  border-radius: var(--radius-sm);
  padding: 0 0.8rem;
  color: var(--text-secondary);
  font-size: 0.75rem;
  font-weight: 750;
  transition:
    background-color var(--duration-slow) var(--ease-emphasized),
    color var(--duration-slow) var(--ease-emphasized),
    transform var(--duration-slow) var(--ease-emphasized);
  transform: scale(1);
}

.resource-canvas__filter:hover {
  background: var(--space-elevated);
  color: var(--text-primary);
  transform: scale(1.04);
}

.resource-canvas__filter--active {
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
  transform: scale(1.02);
}

.resource-canvas__filter-count {
  display: inline-flex;
  min-width: 1.25rem;
  height: 1.25rem;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, currentColor 10%, transparent);
  padding: 0 0.3rem;
  font-family: var(--font-mono);
  font-size: 0.65rem;
  line-height: 1;
}

@media (max-width: 767px) {
  .resource-canvas__heading-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .resource-canvas__actions {
    width: 100%;
    overflow-x: auto;
  }

  .resource-canvas__status {
    overflow-x: auto;
  }

  .resource-canvas__metric--progress,
  .resource-canvas__guidance {
    display: none;
  }

  .resource-canvas__nodes {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.4rem;
  }

  .resource-canvas__filters {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.4rem;
  }

  .resource-canvas__filter-scroll {
    width: 100%;
  }
}

/* 页面切换动效 */
.resource-canvas__grid--multiple > div,
.space-y-6 > div {
  animation: pageIn 500ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
  opacity: 0;
  transform: translateY(14px);
}
.space-y-6 > div:nth-child(1) { animation-delay: 0ms; }
.space-y-6 > div:nth-child(2) { animation-delay: 60ms; }
.space-y-6 > div:nth-child(3) { animation-delay: 120ms; }
.space-y-6 > div:nth-child(4) { animation-delay: 180ms; }
.space-y-6 > div:nth-child(5) { animation-delay: 240ms; }

@keyframes pageIn {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
