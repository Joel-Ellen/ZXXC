<template>
  <section class="flex h-full min-h-0 flex-col bg-[#0C0D13] px-6 pb-6 pt-6 shadow-[inset_0_2px_12px_rgba(0,0,0,0.8)]">
    <header class="pb-5">
      <p class="text-[10px] font-black uppercase tracking-[-0.05em] text-[#4A4F68]">TUTOR CHANNEL</p>
      <h2 class="mt-2 text-[24px] font-black uppercase tracking-[-0.05em] text-[#F0F3FB]">Tray Interface</h2>
      <p class="mt-2 max-w-[28ch] text-xs font-light leading-6 text-[#4A4F68]">
        Probe prompts, tutoring dialogue, and agent feedback are embedded directly into the tray.
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
          v-for="message in messages"
          :key="message.id"
          class="flex"
          :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
        >
          <div
            class="max-w-[92%]"
            :class="message.role === 'user'
              ? 'rounded-[18px] border border-white/[0.04] bg-[linear-gradient(135deg,rgba(12,55,69,0.92),rgba(22,20,44,0.92))] px-4 py-3 shadow-[0_10px_28px_rgba(0,0,0,0.28)]'
              : 'pl-0'"
          >
            <div
              v-if="message.role === 'assistant'"
              class="border-l-[1.5px] border-aurora-mint/55 py-1 pl-4 shadow-[inset_1.5px_0_10px_rgba(0,242,254,0.05)]"
            >
              <div class="mb-2 text-[10px] font-mono uppercase tracking-[0.2em] text-aurora-mint/75">
                Tutor Agent
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

            <p
              v-else
              class="whitespace-pre-wrap text-sm font-light leading-7 text-[#F0F3FB]"
            >
              {{ message.content }}
            </p>
          </div>
        </article>
      </div>
    </div>

    <footer class="pt-5">
      <div class="rounded-[22px] border border-white/[0.03] bg-white/[0.015] p-3 shadow-[inset_0_1px_10px_rgba(0,0,0,0.6)]">
        <div class="flex items-end gap-3">
          <label class="sr-only" for="chat-input">Tutor input</label>
          <textarea
            id="chat-input"
            v-model="draft"
            class="focus-ring min-h-[108px] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm font-light leading-7 text-[#E2E6F3] placeholder:text-[#4A4F68]"
            :disabled="bootMode === 'probe' || busy"
            placeholder="Ask about a node, a code path, or why a concept behaves the way it does."
            @keydown.enter.exact.prevent="submit"
          />
          <button
            type="button"
            class="focus-ring rounded-full border border-white/[0.05] bg-[linear-gradient(135deg,rgba(0,242,254,0.28),rgba(127,0,255,0.42))] px-5 py-3 text-[11px] font-black uppercase tracking-[0.14em] text-white transition active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="bootMode === 'probe' || busy || !draft.trim()"
            @click="submit"
          >
            {{ busy ? "Routing" : "Dispatch" }}
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
