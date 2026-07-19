<template>
  <section class="flex h-full min-h-0 flex-col" @wheel="forwardWheelToMessages">
    <!-- 头部 -->
    <header class="shrink-0 flex items-center justify-between gap-3 px-5 pt-4 pb-3">
      <h2 class="text-base font-bold text-text-primary">学习辅导</h2>
      <button
        v-if="collapsible"
        type="button"
        class="focus-ring rounded-lg px-3 py-1.5 text-sm font-medium text-text-muted hover:text-text-primary transition-colors"
        @click="$emit('collapse')"
      >
        收起
      </button>
    </header>

    <!-- 内容区 -->
    <div
      ref="scrollRoot"
      class="min-h-0 flex-1 px-5"
      :class="messages.length ? 'overflow-y-auto' : 'overflow-y-hidden'"
      data-chat-scroll="true"
      @scroll.passive="handleScroll"
    >
      <ProbeDeck
        v-if="bootMode === 'probe' && probe"
        :probe="probe"
        :collected="probeCollected"
        :total="probeTotal"
        :submitting="isSubmittingProbe"
        @submit="$emit('submit-probe', $event)"
      />

      <!-- 空状态 -->
      <div v-else-if="!messages.length" class="h-full flex flex-col pt-6">
        <p class="text-sm font-semibold text-text-primary">你可以这样问我</p>
        <div class="mt-4 space-y-2.5">
          <button
            v-for="prompt in quickPrompts"
            :key="`empty-${prompt}`"
            type="button"
            class="focus-ring block w-full rounded-xl border border-subtle px-4 py-3 text-left text-sm text-text-muted transition-colors hover:text-text-primary hover:border-primary/25 hover:bg-card-hover"
            :disabled="busy"
            @click="sendPrompt(prompt)"
          >
            {{ prompt }}
          </button>
        </div>
      </div>

      <!-- 消息列表 -->
      <div v-else class="py-3 space-y-7">
        <article
          v-for="(message, index) in messages"
          :key="message.id"
          class="flex"
          :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
        >
          <div :class="message.role === 'user' ? 'max-w-[85%]' : 'max-w-[92%]'">
            <div
              v-if="message.role === 'assistant'"
              class="text-sm leading-7 text-text-primary"
            >
              <StreamText
                v-if="message.isStreaming && message.tokenStream"
                :token-stream="message.tokenStream"
              />
              <div
                v-else-if="message.isStreaming && !message.content"
                class="flex items-center gap-1.5 py-1"
              >
                <span class="generating-dot" />
                <span class="generating-dot" />
                <span class="generating-dot" />
              </div>
              <div v-else-if="message.isStreaming && message.content">
                <MarkdownContent :content="message.content" />
                <span class="streaming-cursor" aria-hidden="true" />
              </div>
              <MarkdownContent
                v-else
                :content="message.content"
                :mermaid-source="message.mermaidSource"
              />
            </div>
            <div
              v-else
              class="rounded-2xl bg-card-hover border border-subtle px-4 py-3"
            >
              <p class="whitespace-pre-wrap text-sm leading-7 text-text-primary">
                {{ message.content }}
              </p>
            </div>
          </div>
        </article>
        <div class="h-2" />
      </div>
    </div>

    <!-- 底部 -->
    <footer class="shrink-0 px-4 pb-4 pt-1.5 space-y-2.5">
      <!-- 模式选择 -->
      <div v-if="bootMode !== 'probe'" class="flex flex-wrap gap-2">
        <button
          v-for="ctx in contextTypes"
          :key="ctx.value"
          type="button"
          class="focus-ring rounded-full px-3.5 py-1.5 text-sm transition-colors"
          :class="selectedContext === ctx.value
            ? 'bg-primary-soft text-primary font-medium'
            : 'text-text-muted hover:text-text-secondary'"
          @click="selectContext(ctx.value)"
        >
          {{ ctx.label }}
        </button>
      </div>

      <!-- 代码调试 -->
      <div v-if="selectedContext === 'code_debug' && bootMode !== 'probe'" class="space-y-2.5">
        <textarea
          v-model="codeSnippet"
          class="focus-ring w-full rounded-xl border border-subtle bg-card px-4 py-3 font-mono text-sm text-text-primary placeholder:text-text-muted resize-none"
          rows="5"
          placeholder="粘贴代码..."
          @input="markDraftDirty"
        />
        <div class="flex gap-2">
          <input
            v-model="errorMessage"
            class="focus-ring flex-1 rounded-xl border border-subtle bg-card px-4 py-3 text-sm text-text-primary placeholder:text-text-muted"
            placeholder="报错信息（可选）"
            @input="markDraftDirty"
          />
          <button
            type="button"
            class="btn-ripple focus-ring btn-capsule shrink-0"
            :disabled="busy || !codeSnippet.trim()"
            @click="submitCodeDebug"
          >
            <span v-if="busy" class="flex items-center gap-1.5">
              <span class="generating-dot" style="width:4px;height:4px" />
              <span class="generating-dot" style="width:4px;height:4px;animation-delay:.15s" />
              <span class="generating-dot" style="width:4px;height:4px;animation-delay:.3s" />
            </span>
            <span v-else>调试</span>
          </button>
        </div>
      </div>

      <!-- 输入区 -->
      <div v-if="selectedContext !== 'code_debug'" class="flex items-end gap-3">
        <textarea
          id="chat-input"
          v-model="draft"
          class="focus-ring min-h-[80px] max-h-[160px] flex-1 resize-none rounded-xl border border-subtle bg-card px-4 py-3.5 text-sm text-text-primary placeholder:text-text-muted leading-7"
          :disabled="bootMode === 'probe' || busy"
          :placeholder="inputPlaceholder"
          rows="1"
          @keydown.enter.exact.prevent="submit"
          @input="onDraftInput"
        />
        <button
          type="button"
          class="btn-ripple focus-ring btn-capsule shrink-0"
          :disabled="bootMode === 'probe' || busy || !draft.trim()"
          @click="submit"
        >
          发送
        </button>
      </div>
    </footer>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import MarkdownContent from "./MarkdownContent.vue";
import ProbeDeck from "./ProbeDeck.vue";
import StreamText from "./StreamText.vue";
import { useLearningAssetsStore } from "../stores/learningAssets";

const props = defineProps({
  messages: { type: Array, default: () => [] },
  bootMode: { type: String, default: "loading" },
  probe: { type: Object, default: null },
  probeCollected: { type: Number, default: 0 },
  probeTotal: { type: Number, default: 6 },
  isSubmittingProbe: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  sessionId: { type: String, default: "" },
  nodeId: { type: String, default: "" },
  nodeTitle: { type: String, default: "" },
  suggestions: { type: Array, default: () => [] },
  collapsible: { type: Boolean, default: false },
});

const emit = defineEmits(["send", "submit-probe", "collapse"]);

const draft = ref("");
const scrollRoot = ref(null);
const isPinnedToBottom = ref(true);
const learningAssets = useLearningAssetsStore();
const restoredDraftKey = ref("");
const draftDirty = ref(false);
const restoringDraft = ref(false);
let draftSaveTimer = null;
let scrollSaveTimer = null;

// 上下文类型选择器（来自旧 Tutor.vue）
const contextTypes = [
  { value: "concept", label: "概念讲解" },
  { value: "problem_solving", label: "解题思路" },
  { value: "study_advice", label: "学习建议" },
  { value: "exam_prep", label: "考前冲刺" },
  { value: "code_debug", label: "代码调试" },
];
const selectedContext = ref("concept");
const codeSnippet = ref("");
const errorMessage = ref("");
const assetContext = computed(() => createAssetContext(props.sessionId, props.nodeId));

const quickPrompts = computed(() => {
  if (props.suggestions.length) {
    return props.suggestions.slice(0, 4);
  }

  const label = props.nodeTitle || "当前知识点";
  return [
    `帮我梳理 ${label} 的核心概念`,
    `用更直观的方式解释 ${label}`,
    `给我一个 ${label} 的练习顺序`,
  ];
});

const modeLabel = computed(() => (props.bootMode === "probe" ? "入学诊断" : "学习辅导"));
const modeHint = computed(() => (
  props.bootMode === "probe"
    ? `已完成 ${Math.min(props.probeCollected, props.probeTotal)}/${props.probeTotal}`
    : (props.nodeTitle ? `聚焦节点：${props.nodeTitle}` : "等待学习节点")
));
const inputPlaceholder = computed(() => (
  props.bootMode === "probe"
    ? "完成当前测评后即可进入辅导问答。"
    : "问点什么好呢..."
));
const footerHint = computed(() => (
  props.bootMode === "probe"
    ? "测评结束后会自动切换到学习辅导。"
    : "建议围绕当前节点提问，反馈会更聚焦。"
));

watch(
  () => props.bootMode,
  (mode) => {
    if (mode === "probe") {
      persistDraft();
      resetDraftEditor();
      draftDirty.value = false;
    }
  },
);

watch(
  () => [props.sessionId, props.nodeId],
  ([nextSessionId, nextNodeId], previousScope) => {
    const nextContext = createAssetContext(nextSessionId, nextNodeId);
    const previousContext = previousScope
      ? createAssetContext(previousScope[0], previousScope[1])
      : null;

    if (previousContext && previousContext.scopeKey !== nextContext.scopeKey) {
      cancelAssetSaveTimers();
      persistDraft(previousContext);
      persistScrollPosition(previousContext);
    }

    restoredDraftKey.value = "";
    draftDirty.value = false;
    resetDraftEditor();
    restoreDraft(nextContext);
    void restoreScrollPosition(nextContext);
  },
  { immediate: true },
);

watch(
  () => [learningAssets.sessionId, learningAssets.hydrated],
  () => {
    const context = assetContext.value;
    restoreDraft(context);
    void restoreScrollPosition(context);
  },
);

watch(
  [draft, selectedContext, codeSnippet, errorMessage],
  () => {
    if (!restoringDraft.value && draftDirty.value) {
      scheduleDraftSave();
    }
  },
);

watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    if (shouldAutoScroll()) {
      scrollToBottom();
    }
  },
);

watch(
  () => [
    props.messages.at(-1)?.id ?? "",
    props.messages.at(-1)?.content ?? "",
    props.messages.at(-1)?.tokenStream ?? "",
    props.messages.at(-1)?.isStreaming ?? false,
  ],
  async () => {
    await nextTick();
    if (shouldAutoScroll()) {
      scrollToBottom();
    }
  },
);

function autoResize(e) {
  const el = e.target;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

function onDraftInput(e) {
  autoResize(e);
  markDraftDirty();
}

function markDraftDirty() {
  if (restoringDraft.value) return;
  draftDirty.value = true;
  scheduleDraftSave();
}

function selectContext(contextType) {
  markDraftDirty();
  selectedContext.value = selectedContext.value === contextType ? "concept" : contextType;
}

function submit() {
  const value = draft.value.trim();
  if (!value) {
    return;
  }

  isPinnedToBottom.value = true;
  emit("send", {
    text: value,
    contextType: selectedContext.value,
    codeSnippet: selectedContext.value === "code_debug" ? codeSnippet.value : "",
    errorMessage: selectedContext.value === "code_debug" ? errorMessage.value : "",
  });
  clearDraft();
  resetDraftEditor();
  draftDirty.value = false;
  const el = document.getElementById("chat-input");
  if (el) el.style.height = "auto";
}

function submitCodeDebug() {
  const snippet = codeSnippet.value.trim();
  if (!snippet || props.busy || props.bootMode === "probe") {
    return;
  }

  const error = errorMessage.value.trim();
  isPinnedToBottom.value = true;
  emit("send", {
    text: error ? "请根据错误信息调试这段代码" : "请分析并调试这段代码",
    contextType: "code_debug",
    codeSnippet: snippet,
    errorMessage: error,
  });
  clearDraft();
  resetDraftEditor();
  draftDirty.value = false;
}

function sendPrompt(prompt) {
  if (!prompt || props.busy || props.bootMode === "probe") {
    return;
  }

  isPinnedToBottom.value = true;
  emit("send", {
    text: prompt,
    contextType: "concept",
    codeSnippet: "",
    errorMessage: "",
  });
}

function handleScroll() {
  if (!(scrollRoot.value instanceof HTMLElement)) {
    return;
  }

  isPinnedToBottom.value = isNearBottom();
  scheduleScrollSave();
}

function shouldAutoScroll() {
  return isPinnedToBottom.value || props.messages.at(-1)?.role === "user";
}

function isNearBottom() {
  if (!(scrollRoot.value instanceof HTMLElement)) {
    return true;
  }

  const threshold = 48;
  const distance = scrollRoot.value.scrollHeight - scrollRoot.value.scrollTop - scrollRoot.value.clientHeight;
  return distance <= threshold;
}

function scrollToBottom() {
  if (!(scrollRoot.value instanceof HTMLElement)) {
    return;
  }

  scrollRoot.value.scrollTop = scrollRoot.value.scrollHeight;
  isPinnedToBottom.value = true;
}

function forwardWheelToMessages(event) {
  if (!(scrollRoot.value instanceof HTMLElement)) {
    return;
  }

  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }

  if (scrollRoot.value.contains(target)) {
    return;
  }

  if (target.closest("textarea, input, select, [contenteditable='true']")) {
    return;
  }

  scrollRoot.value.scrollTop += event.deltaY;
}

onMounted(() => {
  const context = assetContext.value;
  restoreDraft(context);
  void restoreScrollPosition(context);
  nextTick(() => scrollToBottom());
});

onBeforeUnmount(() => {
  void flushLearningAssets();
});

function createAssetContext(sessionId, nodeId) {
  const normalizedSessionId = String(sessionId || "");
  const normalizedNodeId = String(nodeId || "");
  const nodeScope = normalizedNodeId || "course";
  return Object.freeze({
    sessionId: normalizedSessionId,
    nodeId: normalizedNodeId,
    scopeKey: `${normalizedSessionId}:${nodeScope}`,
    draftKey: `tutor:${nodeScope}`,
    scrollKey: `chat:${nodeScope}`,
  });
}

function canUseAssetContext(context) {
  return Boolean(
    context?.sessionId
    && context.sessionId === String(learningAssets.sessionId || ""),
  );
}

function isCurrentAssetContext(context) {
  return Boolean(context && context.scopeKey === assetContext.value.scopeKey);
}

function restoreDraft(context = assetContext.value) {
  const restoreKey = `${context.sessionId}:${context.draftKey}:${learningAssets.hydrated ? "remote" : "cache"}`;
  if (
    !canUseAssetContext(context)
    || !isCurrentAssetContext(context)
    || draftDirty.value
    || restoredDraftKey.value === restoreKey
  ) return;

  const saved = learningAssets.read("drafts", context.draftKey, null);
  if (!saved || typeof saved !== "object") {
    restoredDraftKey.value = restoreKey;
    return;
  }

  restoringDraft.value = true;
  draft.value = typeof saved.content === "string" ? saved.content : "";
  selectedContext.value = typeof saved.context_type === "string" && saved.context_type
    ? saved.context_type
    : "concept";
  codeSnippet.value = typeof saved.code_snippet === "string" ? saved.code_snippet : "";
  errorMessage.value = typeof saved.error_message === "string" ? saved.error_message : "";
  restoringDraft.value = false;
  restoredDraftKey.value = restoreKey;
}

function resetDraftEditor() {
  restoringDraft.value = true;
  draft.value = "";
  selectedContext.value = "concept";
  codeSnippet.value = "";
  errorMessage.value = "";
  restoringDraft.value = false;
}

function scheduleDraftSave() {
  if (draftSaveTimer) window.clearTimeout(draftSaveTimer);
  const context = assetContext.value;
  draftSaveTimer = window.setTimeout(() => {
    draftSaveTimer = null;
    persistDraft(context);
  }, 300);
}

function persistDraft(context = assetContext.value) {
  if (!canUseAssetContext(context)) return;
  const hasContent = Boolean(draft.value || codeSnippet.value || errorMessage.value);
  if (!hasContent) {
    learningAssets.remove("drafts", context.draftKey);
    return;
  }

  learningAssets.write("drafts", context.draftKey, {
    node_id: context.nodeId,
    kind: "tutor",
    content: draft.value,
    context_type: selectedContext.value,
    code_snippet: codeSnippet.value,
    error_message: errorMessage.value,
  });
}

function clearDraft(context = assetContext.value) {
  if (draftSaveTimer) {
    window.clearTimeout(draftSaveTimer);
    draftSaveTimer = null;
  }
  learningAssets.remove("drafts", context.draftKey);
}

function scheduleScrollSave() {
  if (scrollSaveTimer) return;
  const context = assetContext.value;
  scrollSaveTimer = window.setTimeout(() => {
    scrollSaveTimer = null;
    persistScrollPosition(context);
  }, 250);
}

function persistScrollPosition(context = assetContext.value) {
  if (!(scrollRoot.value instanceof HTMLElement)) return;
  if (!canUseAssetContext(context)) return;
  learningAssets.write("scroll_positions", context.scrollKey, {
    node_id: context.nodeId,
    top: Math.max(0, Math.round(scrollRoot.value.scrollTop)),
  });
}

async function restoreScrollPosition(context = assetContext.value) {
  await nextTick();
  if (!(scrollRoot.value instanceof HTMLElement)) return;
  if (!canUseAssetContext(context) || !isCurrentAssetContext(context)) return;
  const saved = learningAssets.read("scroll_positions", context.scrollKey, null);
  const top = Number(saved?.top);
  if (Number.isFinite(top) && top > 0) {
    scrollRoot.value.scrollTop = top;
    isPinnedToBottom.value = isNearBottom();
  }
}

function cancelAssetSaveTimers() {
  if (draftSaveTimer) {
    window.clearTimeout(draftSaveTimer);
    draftSaveTimer = null;
  }
  if (scrollSaveTimer) {
    window.clearTimeout(scrollSaveTimer);
    scrollSaveTimer = null;
  }
}

function flushLearningAssets() {
  cancelAssetSaveTimers();
  const context = assetContext.value;
  persistDraft(context);
  persistScrollPosition(context);
  return learningAssets.flush();
}

defineExpose({ flushLearningAssets });
</script>
