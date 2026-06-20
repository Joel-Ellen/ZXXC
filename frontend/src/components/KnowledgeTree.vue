<template>
  <div class="space-y-3">
    <button
      v-for="node in nodes"
      :key="node.id"
      type="button"
      class="focus-ring group relative flex w-full items-start gap-4 overflow-hidden rounded-[18px] px-4 py-4 text-left transition-all duration-300 hover:translate-x-[2px] active:scale-[0.99]"
      :class="buttonClass(node)"
      @click="$emit('select', node.id)"
    >
      <div class="absolute inset-y-4 left-0 w-px bg-gradient-to-b from-transparent via-[var(--border-strong)] to-transparent" />

      <span class="mt-0.5 w-8 text-[13px] font-mono uppercase tracking-[0.14em] text-text-muted">
        {{ String(node.order).padStart(2, "0") }}
      </span>

      <span
        class="relative mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-subtle bg-card"
      >
        <IconCheck
          v-if="node.mastery >= 0.65"
          class="text-success"
          :size="16"
        />
        <IconLock
          v-else-if="isLocked(node)"
          class="text-text-muted"
          :size="16"
        />
        <span
          v-else
          class="h-2 w-2 rounded-full"
          :class="node.id === currentNode ? 'bg-secondary shadow-[0_0_10px_var(--color-secondary)]' : 'bg-primary shadow-[0_0_10px_var(--color-primary)]'"
        />
      </span>

      <span class="min-w-0 flex-1">
        <span class="block truncate text-[15px] font-medium leading-6 text-text-primary">{{ node.title }}</span>
        <span class="mt-1 block text-[12px] font-light tracking-[0.08em] text-text-muted">
          {{ node.mastery >= 0.65 ? "已掌握" : `掌握度 ${Math.round(node.mastery * 100)}%` }}
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
    return "border border-secondary/25 bg-gradient-to-br from-secondary-soft to-transparent shadow-card";
  }
  if (node.mastery >= 0.65) {
    return "border border-success/20 bg-gradient-to-b from-success-soft to-transparent";
  }
  if (isLocked(node)) {
    return "border border-subtle bg-card opacity-70";
  }
  return "border border-subtle bg-card hover:border-hover hover:bg-card-hover";
}
</script>
