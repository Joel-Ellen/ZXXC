<template>
  <section class="flex h-full min-h-0 flex-col px-4 py-4 sm:px-5" @wheel="forwardWheelToMessages">
    <header class="shrink-0 pb-4">
      <div class="flex items-start justify-between gap-4">
        <div class="min-w-0">
          <p class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">辅导通道</p>
          <h2 class="mt-2 text-[24px] font-black tracking-tight text-text-primary">学习托盘</h2>
          <p class="mt-2 max-w-[34ch] text-xs font-light leading-6 text-text-muted">
            冷启动测评、过程追问和智能反馈都会在这里汇总，保证学习动作始终可回看、可追问、可延续。
          </p>
        </div>

        <div class="workspace-shell-card hidden rounded-[18px] px-4 py-3 text-right 2xl:block">
          <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">当前模式</p>
          <p class="mt-2 text-sm font-semibold text-text-primary">{{ modeLabel }}</p>
          <p class="mt-1 text-[11px] text-text-muted">{{ modeHint }}</p>
        </div>
      </div>

      <div
        v-if="bootMode !== 'probe' && quickPrompts.length"
        class="aurora-scroll mt-4 flex gap-2 overflow-x-auto pb-1"
      >
        <button
          v-for="prompt in quickPrompts"
          :key="prompt"
          type="button"
          class="workspace-shell-btn focus-ring shrink-0 px-3 py-1.5 text-[11px] font-medium"
          :disabled="busy"
          @click="sendPrompt(prompt)"
        >
          {{ prompt }}
        </button>
      </div>

      <div v-if="bootMode !== 'probe'" class="mt-4 grid gap-3 lg:grid-cols-2">
        <div class="workspace-shell-card-soft rounded-[18px] px-4 py-3">
          <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">当前模式</p>
          <p class="mt-2 text-sm font-semibold text-text-primary">{{ modeLabel }}</p>
          <p class="mt-1 text-[11px] leading-5 text-text-muted">{{ modeHint }}</p>
        </div>
        <div class="workspace-shell-card-soft rounded-[18px] px-4 py-3">
          <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">提问建议</p>
          <p class="mt-2 text-[11px] leading-5 text-text-muted">{{ footerHint }}</p>
        </div>
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
            :disabled="busy"
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
          class="flex animate-slideUp"
          :style="{ animationDelay: `${index * 40}ms` }"
          :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
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

              <div
                v-else-if="message.isStreaming && !message.content"
                class="rounded-2xl border border-subtle bg-space-surface/40 px-4 py-3 text-sm text-text-muted"
              >
                正在整理当前节点的讲解脉络...
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
          @click="selectedContext = selectedContext === ctx.value ? 'concept' : ctx.value"
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
          rows="4"
          placeholder="粘贴需要调试的代码..."
        />
        <label class="mb-1 block text-xs font-semibold text-text-secondary">错误信息（可选）</label>
        <input
          v-model="errorMessage"
          class="workspace-shell-input focus-ring w-full rounded-xl px-3 py-2 text-xs text-text-primary placeholder:text-text-muted"
          placeholder="粘贴报错信息..."
        />
      </div>

      <div class="workspace-shell-card rounded-[24px] p-2.5">
        <div class="flex items-end gap-3">
          <label class="sr-only" for="chat-input">辅导输入框</label>
          <textarea
            id="chat-input"
            v-model="draft"
            class="focus-ring min-h-[72px] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm font-light leading-7 text-text-primary placeholder:text-text-muted sm:min-h-[68px]"
            :disabled="bootMode === 'probe' || busy"
            :placeholder="inputPlaceholder"
            @keydown.enter.exact.prevent="submit"
          />
          <button
            type="button"
            class="focus-ring btn-capsule shrink-0"
            :disabled="bootMode === 'probe' || busy || !draft.trim()"
            @click="submit"
          >
            {{ busy ? "调度中" : "发送" }}
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
import { computed, nextTick, ref, watch } from "vue";
import MarkdownContent from "./MarkdownContent.vue";
import ProbeDeck from "./ProbeDeck.vue";
import StreamText from "./StreamText.vue";

const props = defineProps({
  messages: { type: Array, default: () => [] },
  bootMode: { type: String, default: "loading" },
  probe: { type: Object, default: null },
  probeCollected: { type: Number, default: 0 },
  probeTotal: { type: Number, default: 6 },
  isSubmittingProbe: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  nodeTitle: { type: String, default: "" },
  suggestions: { type: Array, default: () => [] },
});

const emit = defineEmits(["send", "submit-probe"]);

const draft = ref("");
const scrollRoot = ref(null);
const isPinnedToBottom = ref(true);

// 上下文类型选择器（来自旧 Tutor.vue）
const contextTypes = [
  { value: "concept", label: "概念讲解" },
  { value: "problem_solving", label: "解题思路" },
  { value: "code_debug", label: "代码调试" },
  { value: "study_advice", label: "学习建议" },
  { value: "exam_prep", label: "考前冲刺" },
];
const selectedContext = ref("concept");
const codeSnippet = ref("");
const errorMessage = ref("");

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
      draft.value = "";
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
  draft.value = "";
  if (selectedContext.value === "code_debug") {
    codeSnippet.value = "";
    errorMessage.value = "";
  }
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
</script>
