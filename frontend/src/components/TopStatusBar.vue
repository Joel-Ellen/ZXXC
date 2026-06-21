<template>
  <div class="aurora-scroll flex items-center gap-2 overflow-x-auto" aria-live="polite">
    <transition-group name="status-pill" tag="div" class="flex items-center gap-2">
      <span
        v-for="status in statuses"
        :key="status.key"
        class="inline-flex items-center gap-2 rounded-full border-[0.5px] bg-card px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.10em] backdrop-blur-sm transition-all duration-200"
        :class="statusClass(status)"
      >
        <span
          class="h-1.5 w-1.5 rounded-full"
          :class="dotClass(status).class"
          :style="dotClass(status).style"
        />
        <component :is="iconForStatus(status)" class="shrink-0 opacity-80" :size="14" />
        <span class="font-semibold text-text-primary">{{ status.label }}</span>
        <span class="text-text-muted">{{ status.phase }}</span>
        <span v-if="status.progress > 0" class="font-mono text-text-muted">{{ status.progress }}%</span>
      </span>
    </transition-group>
  </div>
</template>

<script setup>
import IconDoc from "./icons/IconDoc.vue";
import IconQuiz from "./icons/IconQuiz.vue";
import IconTree from "./icons/IconTree.vue";

defineProps({
  statuses: {
    type: Array,
    default: () => [],
  },
});

const GLOW_COLORS = {
  primary: "var(--color-primary)",
  secondary: "var(--color-secondary)",
  tertiary: "var(--color-tertiary)",
  success: "var(--color-success)",
  warning: "var(--color-warning)",
  error: "var(--color-error)",
  info: "var(--color-info)",
};

const BORDER_CLASSES = {
  primary: "border-primary/30 text-primary",
  secondary: "border-secondary/30 text-secondary",
  tertiary: "border-tertiary/30 text-tertiary",
  success: "border-success/30 text-success",
  warning: "border-warning/30 text-warning",
  error: "border-error/30 text-error",
  info: "border-info/30 text-info",
};

const DOT_CLASSES = {
  primary: "bg-primary",
  secondary: "bg-secondary",
  tertiary: "bg-tertiary",
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error",
  info: "bg-info",
};

function statusKindColor(kind) {
  return kind === "quiz" ? "secondary" : "primary";
}

function iconForStatus(status) {
  if (status.kind === "quiz") {
    return IconQuiz;
  }

  if (status.kind === "path") {
    return IconTree;
  }

  return IconDoc;
}

function statusPhaseColor(status) {
  if (status.phase === "error" || status.phase === "failed") return "error";
  if (status.phase === "done" || status.phase === "completed" || status.progress === 100) return "success";
  if (status.active) return statusKindColor(status.kind);
  return null;
}

function dotClass(status) {
  const phaseColor = statusPhaseColor(status);
  if (!phaseColor) {
    return { class: "bg-text-muted/40", style: {} };
  }
  const animate = status.active && phaseColor !== "success" && phaseColor !== "error" ? " animate-breathe" : "";
  return {
    class: `${DOT_CLASSES[phaseColor]}${animate}`,
    style: { boxShadow: `0 0 10px ${GLOW_COLORS[phaseColor]}` },
  };
}

function statusClass(status) {
  const phaseColor = statusPhaseColor(status);
  if (phaseColor) {
    return BORDER_CLASSES[phaseColor];
  }
  return "border-subtle text-text-muted";
}
</script>

<style scoped>
.status-pill-enter-active,
.status-pill-leave-active {
  transition: all 260ms cubic-bezier(0.16, 1, 0.3, 1);
}

.status-pill-enter-from,
.status-pill-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.96);
}
</style>
