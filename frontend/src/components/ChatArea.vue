<template>
  <section class="flex h-full min-h-0 flex-col px-3 py-3 sm:px-4" @wheel="forwardWheelToMessages">
    <header class="shrink-0 pb-3">
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <p class="text-[10px] font-bold text-text-muted">辅导通道</p>
          <h2 class="mt-1 truncate text-base font-bold text-text-primary">学习辅导</h2>
        </div>

        <div class="flex shrink-0 items-center gap-2">
          <button
            v-if="collapsible"
            type="button"
            class="workspace-shell-btn focus-ring min-h-9 px-2.5 text-[11px] font-semibold"
            aria-label="收起辅导区域"
            title="收起辅导区域"
            @click="$emit('collapse')"
          >
            收起
          </button>
          <span class="workspace-shell-chip workspace-shell-chip--accent shrink-0 px-2.5 py-1 text-[10px] font-semibold">
            {{ modeLabel }}
          </span>
        </div>
      </div>

      <div
        v-if="bootMode !== 'probe' && quickPrompts.length"
        class="aurora-scroll mt-3 flex gap-2 overflow-x-auto pb-1"
      >
        <button
          v-for="prompt in quickPrompts"
          :key="prompt"
          type="button"
          class="workspace-shell-btn focus-ring shrink-0 px-3 py-1.5 text-[11px] font-medium"
          :disabled="busy || sendPending"
          @click="sendPrompt(prompt)"
        >
          {{ prompt }}
        </button>
      </div>
    </header>

    <div
      ref="scrollRoot"
      class="aurora-scroll min-h-0 flex-1 overflow-y-auto pr-1"
      data-chat-scroll="true"
      aria-live="polite"
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

      <div
        v-else-if="!messages.length"
        class="workspace-shell-card rounded-[24px] p-5"
      >
        <div class="flex items-start gap-4">
          <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary-soft text-primary">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M12 5v14M5 12h14" stroke-linecap="round" />
            </svg>
          </div>
          <div class="min-w-0">
            <p class="text-sm font-semibold text-text-primary">从当前节点开始提问</p>
            <p class="mt-2 text-sm leading-7 text-text-muted">
              你可以让辅导智能体解释概念、拆解代码、总结本节点和上一节点的关系，或者直接给出下一步练习建议。
            </p>
          </div>
        </div>

        <div class="mt-4 grid gap-3">
          <button
            v-for="prompt in quickPrompts"
            :key="`empty-${prompt}`"
            type="button"
            class="workspace-shell-card-soft focus-ring rounded-[18px] px-4 py-3 text-left text-sm text-text-secondary transition-all duration-200 hover:text-text-primary"
            :disabled="busy || sendPending"
            @click="sendPrompt(prompt)"
          >
            {{ prompt }}
          </button>
        </div>
      </div>

      <div v-else class="space-y-6">
        <article
          v-for="(message, index) in messages"
          :key="message.id"
          class="flex"
          :class="[
            message.role === 'user' ? 'justify-end msg-user-enter' : 'justify-start msg-assistant-enter',
          ]"
          :style="{ animationDelay: `${Math.min(index, 3) * 50}ms` }"
        >
          <div class="max-w-[92%]">
            <div
              v-if="message.role === 'assistant'"
               class="workspace-shell-card rounded-r-2xl rounded-bl-2xl rounded-tl-md border border-primary/20 bg-primary-soft/40 px-4 py-3"
            >
              <div class="mb-2 flex items-center gap-2">
                <span class="h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_10px_var(--color-primary)] animate-breathe" />
                <span class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary/90">辅导智能体</span>
              </div>

              <StreamText
                v-if="message.isStreaming && message.tokenStream"
                :token-stream="message.tokenStream"
              />

              <!-- Streaming typing indicator: three animated dots -->
              <div
                v-else-if="message.isStreaming && !message.content"
                class="flex items-center gap-1.5 py-1"
                aria-label="正在生成..."
              >
                <span class="generating-dot" />
                <span class="generating-dot" />
                <span class="generating-dot" />
              </div>

              <!-- Streaming partial text: show content + cursor -->
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
               class="workspace-shell-card rounded-l-[20px] rounded-br-[20px] rounded-tr-md border border-secondary/20 bg-secondary-soft/40 px-4 py-3 text-right"
            >
              <div class="mb-2 flex items-center justify-end gap-2">
                <span class="text-[10px] font-mono uppercase tracking-[0.2em] text-secondary/90">我</span>
                <span class="h-1.5 w-1.5 rounded-full bg-secondary shadow-[0_0_10px_var(--color-secondary)]" />
              </div>
              <p class="whitespace-pre-wrap text-sm font-light leading-7 text-text-primary">
                {{ message.content }}
              </p>
            </div>
          </div>
        </article>
      </div>
    </div>

    <footer class="shrink-0 pt-3 space-y-3">
      <!-- 上下文类型选择器 -->
      <div v-if="bootMode !== 'probe'" class="flex flex-wrap gap-2">
        <button
          v-for="ctx in contextTypes"
          :key="ctx.value"
          type="button"
          class="focus-ring rounded-full px-3 py-1 text-[11px] font-medium transition-all duration-200"
          :class="selectedContext === ctx.value
            ? 'workspace-shell-btn workspace-shell-btn--accent text-white shadow-sm'
            : 'workspace-shell-btn text-text-muted hover:text-text-secondary'"
          :aria-pressed="String(selectedContext === ctx.value)"
          :disabled="busy || sendPending"
          @click="selectContext(ctx.value)"
        >
          {{ ctx.label }}
        </button>
      </div>

      <!-- 代码调试面板 -->
      <div
        v-if="selectedContext === 'code_debug' && bootMode !== 'probe'"
        class="workspace-shell-card rounded-2xl p-3"
      >
        <label class="mb-1 block text-xs font-semibold text-text-secondary">代码片段</label>
        <textarea
          v-model="codeSnippet"
          class="workspace-shell-input focus-ring mb-2 w-full rounded-xl px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-muted"
          @input="markDraftDirty"
          rows="4"
          :disabled="busy || sendPending"
          placeholder="粘贴需要调试的代码..."
        />
        <label class="mb-1 block text-xs font-semibold text-text-secondary">错误信息（可选）</label>
        <input
          v-model="errorMessage"
          class="workspace-shell-input focus-ring w-full rounded-xl px-3 py-2 text-xs text-text-primary placeholder:text-text-muted"
          @input="markDraftDirty"
          placeholder="粘贴报错信息..."
          :disabled="busy || sendPending"
        />

        <div class="mt-3 flex items-center justify-between gap-3">
          <p class="text-[11px] leading-5 text-text-muted">代码片段为必填，错误信息可选。</p>
          <button
            type="button"
            class="btn-ripple focus-ring btn-capsule shrink-0"
            :disabled="busy || !codeSnippet.trim()"
            @click="submitCodeDebug"
          >
            <span v-if="busy" class="flex items-center gap-1.5">
              <span class="generating-dot" style="width:5px;height:5px" />
              <span class="generating-dot" style="width:5px;height:5px;animation-delay:.15s" />
              <span class="generating-dot" style="width:5px;height:5px;animation-delay:.3s" />
            </span>
            <span v-else>开始调试</span>
          </button>
        </div>
      </div>

      <div
        v-if="sendError"
        class="flex flex-wrap items-center justify-between gap-3 border border-error/30 bg-error-soft px-3 py-2.5 text-xs text-text-primary"
        role="alert"
      >
        <span>{{ sendError }}</span>
        <button
          type="button"
          class="workspace-shell-btn focus-ring px-3 py-2 text-xs font-semibold"
          :disabled="busy || sendPending || !retrySubmission"
          @click="retrySend"
        >
          重新发送
        </button>
      </div>

      <div v-if="selectedContext !== 'code_debug'" class="workspace-shell-card rounded-[24px] p-2.5">
        <div class="flex items-end gap-3">
          <label class="sr-only" for="chat-input">辅导输入框</label>
          <textarea
            id="chat-input"
            v-model="draft"
            class="focus-ring min-h-[72px] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm font-light leading-7 text-text-primary placeholder:text-text-muted sm:min-h-[68px]"
            @input="markDraftDirty"
            :disabled="bootMode === 'probe' || busy || sendPending"
            :placeholder="inputPlaceholder"
            @keydown.enter.exact.prevent="submit"
          />
          <button
            type="button"
            class="btn-ripple focus-ring btn-capsule shrink-0"
            :disabled="bootMode === 'probe' || busy || sendPending || !draft.trim()"
            @click="submit"
          >
            <span v-if="busy || sendPending" class="flex items-center gap-1.5">
              <span class="generating-dot" style="width:5px;height:5px" />
              <span class="generating-dot" style="width:5px;height:5px;animation-delay:.15s" />
              <span class="generating-dot" style="width:5px;height:5px;animation-delay:.3s" />
            </span>
            <span v-else>发送</span>
          </button>
        </div>

        <div class="mt-3 flex flex-wrap items-center justify-between gap-2 px-2">
          <p class="text-[11px] text-text-muted">`Enter` 发送，`Shift + Enter` 换行</p>
          <p class="text-[11px] text-text-muted">{{ footerHint }}</p>
        </div>
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
const sendPending = ref(false);
const sendError = ref("");
const retrySubmission = ref(null);
let draftSaveTimer = null;
let scrollSaveTimer = null;
let sendGeneration = 0;

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
const tutorDraftKey = computed(() => assetContext.value.draftKey);

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
const inputPlaceholder = computed(() => (
  props.bootMode === "probe"
    ? "完成当前测评后即可进入辅导问答。"
    : "询问某个知识点、代码路径，或这个概念为什么要这样设计。"
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
      sendGeneration += 1;
      sendPending.value = false;
      sendError.value = "";
      retrySubmission.value = null;
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

function submit() {
  const value = draft.value.trim();
  if (!value || sendPending.value) {
    return;
  }

  isPinnedToBottom.value = true;
  dispatchSend({
    text: value,
    contextType: selectedContext.value,
    codeSnippet: selectedContext.value === "code_debug" ? codeSnippet.value : "",
    errorMessage: selectedContext.value === "code_debug" ? errorMessage.value : "",
  }, {
    clearEditorOnSuccess: true,
    draftKey: tutorDraftKey.value,
    editorSnapshot: currentEditorSnapshot(),
  });
}

function selectContext(contextType) {
  markDraftDirty();
  selectedContext.value = selectedContext.value === contextType ? "concept" : contextType;
}

function markDraftDirty() {
  if (restoringDraft.value) return;
  sendError.value = "";
  retrySubmission.value = null;
  draftDirty.value = true;
  scheduleDraftSave();
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
  codeSnippet.value = "";
  errorMessage.value = "";
}

function sendPrompt(prompt) {
  if (!prompt || props.busy || sendPending.value || props.bootMode === "probe") {
    return;
  }

  isPinnedToBottom.value = true;
  dispatchSend({
    text: prompt,
    contextType: selectedContext.value,
    codeSnippet: selectedContext.value === "code_debug" ? codeSnippet.value : "",
    errorMessage: selectedContext.value === "code_debug" ? errorMessage.value : "",
  }, {
    clearEditorOnSuccess: false,
    draftKey: tutorDraftKey.value,
  });
}

function dispatchSend(payload, options = {}) {
  if (sendPending.value) return;

  const generation = ++sendGeneration;
  const submission = {
    payload: { ...payload },
    clearEditorOnSuccess: Boolean(options.clearEditorOnSuccess),
    draftKey: String(options.draftKey || "tutor-current"),
    editorSnapshot: options.editorSnapshot ? { ...options.editorSnapshot } : null,
  };
  retrySubmission.value = submission;
  sendPending.value = true;
  sendError.value = "";

  const settle = (success, error) => {
    if (generation !== sendGeneration) return;
    sendPending.value = false;
    if (!success) {
      sendError.value = tutorSendError(error);
      if (submission.draftKey === tutorDraftKey.value) {
        persistDraft(assetContext.value);
      }
      return;
    }

    sendError.value = "";
    retrySubmission.value = null;
    if (!submission.clearEditorOnSuccess) return;

    const sameDraft = submission.draftKey === tutorDraftKey.value
      && editorSnapshotsMatch(currentEditorSnapshot(), submission.editorSnapshot);
    if (!sameDraft) return;

    clearDraft(submission.draftKey);
    resetDraftEditor();
    draftDirty.value = false;
  };

  emit("send", {
    ...submission.payload,
    onSuccess: () => settle(true),
    onFailure: (error) => settle(false, error),
  });
}

function retrySend() {
  if (!retrySubmission.value || sendPending.value) return;
  const submission = retrySubmission.value;
  dispatchSend(submission.payload, submission);
}

function currentEditorSnapshot() {
  return {
    draft: draft.value,
    contextType: selectedContext.value,
    codeSnippet: codeSnippet.value,
    errorMessage: errorMessage.value,
  };
}

function editorSnapshotsMatch(current, sent) {
  return Boolean(sent
    && current.draft === sent.draft
    && current.contextType === sent.contextType
    && current.codeSnippet === sent.codeSnippet
    && current.errorMessage === sent.errorMessage);
}

function tutorSendError(error) {
  const detail = error?.response?.data?.detail || error?.message;
  return typeof detail === "string" && detail.trim()
    ? `发送失败：${detail.trim()}`
    : "发送失败，输入已保留，请重试。";
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
});

onBeforeUnmount(() => {
  sendGeneration += 1;
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

function clearDraft(key = tutorDraftKey.value) {
  if (draftSaveTimer) {
    window.clearTimeout(draftSaveTimer);
    draftSaveTimer = null;
  }
  learningAssets.remove("drafts", key);
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
