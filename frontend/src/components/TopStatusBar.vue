<template>
  <div class="aurora-scroll flex items-center gap-2 overflow-x-auto" aria-live="polite">
    <transition-group name="status-pill" tag="div" class="flex items-center gap-2">
      <span
        v-for="status in statuses"
        :key="status.key"
        class="inline-flex items-center gap-2 rounded-full border bg-transparent px-2.5 py-1 text-[11px] font-light uppercase tracking-[0.14em]"
        :class="statusClass(status)"
      >
        <span
          class="h-1.5 w-1.5 rounded-full"
          :class="status.active ? accentDot(status.kind) : 'bg-white/20'"
        />
        <component :is="status.kind === 'quiz' ? IconQuiz : IconDoc" class="shrink-0" />
        <span class="font-semibold text-[#EEF1FA]">{{ status.label }}</span>
        <span>{{ status.phase }}</span>
        <span v-if="status.progress > 0">{{ status.progress }}%</span>
      </span>
    </transition-group>
  </div>
</template>

<script setup>
import IconDoc from "./icons/IconDoc.vue";
import IconQuiz from "./icons/IconQuiz.vue";

defineProps({
  statuses: {
    type: Array,
    default: () => [],
  },
});

function accentDot(kind) {
  return kind === "quiz" ? "bg-aurora-purple shadow-[0_0_8px_rgba(127,0,255,0.7)]" : "bg-aurora-mint shadow-[0_0_8px_rgba(0,242,254,0.7)]";
}

function statusClass(status) {
  if (status.kind === "quiz") {
    return status.active
      ? "border-aurora-purple/30 text-aurora-purple"
      : "border-white/[0.04] text-[#6B7288]";
  }
  return status.active
    ? "border-aurora-mint/30 text-aurora-mint"
    : "border-white/[0.04] text-[#6B7288]";
}
</script>
