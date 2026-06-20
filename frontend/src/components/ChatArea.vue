<template>
  <section class="flex h-full min-h-0 flex-col px-6 pb-6 pt-6">
    <header class="pb-5">
      <p class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">辅导通道</p>
      <h2 class="mt-2 text-[24px] font-black tracking-tight text-text-primary">学习托盘</h2>
      <p class="mt-2 max-w-[32ch] text-xs font-light leading-6 text-text-muted">
        冷启动测评、辅导对话与智能体反馈都会直接嵌入此托盘。
      </p>
    </header>

    <div class="aurora-scroll flex-1 overflow-y-auto pr-2" aria-live="polite">
      <ProbeDeck
        v-if="bootMode === 'probe' && probe"
        :probe="probe"
        :collected="probeCollected"
        :total="probeTotal"
        :submitting="isSubmittingProbe"
        @submit="$emit('submit-probe', $event)"
      />

      <div class="space-y-6">
        <article
          v-for="(message, index) in messages"
          :key="message.id"
          class="flex animate-slideUp"
          :style="{ animationDelay: `${index * 40}ms` }"
          :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
        >
          <div
            class="max-w-[92%]"
            :class="message.role === 'user' ? 'pr-0' : 'pl-0'"
          >
            <div
              v-if="message.role === 'assistant'"
              class="rounded-r-2xl rounded-bl-2xl rounded-tl-md border-l-[3px] border-primary bg-card py-3 px-4 shadow-card"
            >
              <div class="mb-2 flex items-center gap-2">
                <span class="h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_10px_var(--color-primary)] animate-breathe" />
                <span class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary/90">
                  辅导智能体
                </span>
              </div>
              <StreamText
                v-if="message.isStreaming && message.tokenStream"
                :token-stream="message.tokenStream"
              />
              <MarkdownContent
                v-else
                :content="message.content"
                :mermaid-source="message.mermaidSource"
              />
            </div>

            <div
              v-else
              class="rounded-l-2xl rounded-br-2xl rounded-tr-md border-r-[3px] border-secondary bg-gradient-to-br from-secondary-soft to-card py-3 px-4 text-right shadow-card"
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

    <footer class="pt-5">
      <div class="rounded-[24px] border border-subtle bg-card p-3 shadow-card">
        <div class="flex items-end gap-3">
          <label class="sr-only" for="chat-input">辅导输入框</label>
          <textarea
            id="chat-input"
            v-model="draft"
            class="focus-ring min-h-[108px] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm font-light leading-7 text-text-primary placeholder:text-text-muted"
            :disabled="bootMode === 'probe' || busy"
            placeholder="询问某个知识点、代码路径，或某个概念为何如此工作。"
            @keydown.enter.exact.prevent="submit"
          />
          <button
            type="button"
            class="focus-ring btn-capsule"
            :disabled="bootMode === 'probe' || busy || !draft.trim()"
            @click="submit"
          >
            {{ busy ? "调度中" : "发送" }}
          </button>
        </div>
      </div>
    </footer>
  </section>
</template>

<script setup>
import { ref, watch } from "vue";
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
});

const emit = defineEmits(["send", "submit-probe"]);
const draft = ref("");

watch(
  () => props.bootMode,
  (mode) => {
    if (mode === "probe") {
      draft.value = "";
    }
  },
);

function submit() {
  const value = draft.value.trim();
  if (!value) {
    return;
  }
  emit("send", value);
  draft.value = "";
}
</script>
