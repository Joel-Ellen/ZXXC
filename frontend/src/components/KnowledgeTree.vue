<template>
  <div class="space-y-2.5">
    <button
      v-for="node in nodes"
      :key="node.id"
      type="button"
      class="focus-ring group relative flex w-full items-start gap-3 overflow-hidden rounded-[18px] px-4 py-3 text-left transition duration-300 hover:translate-x-[2px]"
      :class="buttonClass(node)"
      @click="$emit('select', node.id)"
    >
      <div class="absolute inset-y-3 left-0 w-px bg-gradient-to-b from-transparent via-white/[0.06] to-transparent" />

      <span class="mt-0.5 w-7 text-[11px] font-mono uppercase tracking-[0.18em] text-[#5E647B]">
        {{ String(node.order).padStart(2, "0") }}
      </span>

      <span
        class="relative mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-white/[0.06] bg-white/[0.02]"
      >
        <IconCheck
          v-if="node.mastery >= 0.65"
          class="text-aurora-mint"
          :size="14"
        />
        <IconLock
          v-else-if="isLocked(node)"
          class="text-[#5E647B]"
          :size="14"
        />
        <span
          v-else
          class="h-1.5 w-1.5 rounded-full shadow-[0_0_10px_rgba(0,242,254,0.6)]"
          :class="node.id === currentNode ? 'bg-aurora-purple shadow-[0_0_10px_rgba(127,0,255,0.65)]' : 'bg-aurora-mint'"
        />
      </span>

      <span class="min-w-0 flex-1">
        <span class="block truncate text-sm font-medium text-[#EEF2FB]">{{ node.title }}</span>
        <span class="mt-1 block text-[11px] font-light uppercase tracking-[0.12em] text-[#5E647B]">
          {{ node.mastery >= 0.65 ? "Mastered" : `Mastery ${Math.round(node.mastery * 100)}%` }}
        </span>
      </span>
    </button>
  </div>
</template>

<script setup>
import IconCheck from "./icons/IconCheck.vue";
import IconLock from "./icons/IconLock.vue";

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  currentNode: { type: String, default: "" },
});

defineEmits(["select"]);

function isLocked(node) {
  return node.order > 1 && node.mastery < 0.2 && node.id !== props.currentNode;
}

function buttonClass(node) {
  if (node.id === props.currentNode) {
    return "border border-aurora-purple/18 bg-[linear-gradient(135deg,rgba(127,0,255,0.12),rgba(255,255,255,0.02))] shadow-[0_10px_24px_rgba(0,0,0,0.24),inset_0_1px_0_rgba(255,255,255,0.02)]";
  }
  if (node.mastery >= 0.65) {
    return "border border-aurora-mint/14 bg-[linear-gradient(180deg,rgba(0,242,254,0.06),rgba(255,255,255,0.01))]";
  }
  if (isLocked(node)) {
    return "border border-white/[0.03] bg-white/[0.015] opacity-80";
  }
  return "border border-white/[0.03] bg-white/[0.015] hover:border-white/[0.05]";
}
</script>
