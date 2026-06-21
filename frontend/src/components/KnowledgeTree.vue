<template>
  <div class="space-y-4">
    <section class="rounded-[22px] border border-subtle bg-card p-5 shadow-card">
      <div class="flex items-start justify-between gap-4">
        <div>
          <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">学习总览</p>
          <p class="mt-2 text-base font-semibold text-text-primary">{{ summaryTitle }}</p>
          <p class="mt-2 text-sm leading-6 text-text-muted">{{ summaryDetail }}</p>
        </div>

        <div class="rounded-[18px] border border-subtle bg-space-surface/60 px-4 py-3 text-right">
          <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">路径进度</p>
          <p class="mt-2 text-2xl font-black text-text-primary">{{ completionRate }}%</p>
        </div>
      </div>

      <div class="mt-4 rounded-full bg-[var(--border-strong)]/80 p-[1px]">
        <div class="h-2 rounded-full bg-gradient-to-r from-primary via-secondary to-tertiary" :style="{ width: `${completionRate}%` }" />
      </div>

      <div class="mt-4 grid gap-3 sm:grid-cols-3">
        <div
          v-for="stat in stats"
          :key="stat.label"
          class="rounded-[18px] border border-subtle bg-space-surface/40 px-4 py-3"
        >
          <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">{{ stat.label }}</p>
          <p class="mt-2 text-lg font-black text-text-primary">{{ stat.value }}</p>
          <p class="mt-1 text-[11px] leading-5 text-text-muted">{{ stat.detail }}</p>
        </div>
      </div>
    </section>

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
          <span class="flex flex-wrap items-center gap-2">
            <span class="truncate text-[15px] font-medium leading-6 text-text-primary">{{ node.title }}</span>
            <span
              class="rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-[0.08em]"
              :class="statusChipClass(node)"
            >
              {{ statusChipLabel(node) }}
            </span>
          </span>
          <span class="mt-1 block text-[12px] font-light tracking-[0.08em] text-text-muted">
            {{ node.mastery >= 0.65 ? "已掌握，可进入后续节点" : `掌握度 ${Math.round(node.mastery * 100)}%` }}
          </span>
        </span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import IconCheck from "./icons/IconCheck.vue";
import IconLock from "./icons/IconLock.vue";

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  currentNode: { type: String, default: "" },
});

defineEmits(["select"]);

const completedCount = computed(() =>
  props.nodes.filter((node) => node.mastery >= 0.65).length,
);

const activeNode = computed(() =>
  props.nodes.find((node) => node.id === props.currentNode) ?? null,
);

const nextNode = computed(() =>
  props.nodes.find((node) => node.id !== props.currentNode && node.mastery < 0.65) ?? null,
);

const completionRate = computed(() => (
  props.nodes.length ? Math.round((completedCount.value / props.nodes.length) * 100) : 0
));

const summaryTitle = computed(() => (
  activeNode.value ? `当前聚焦：${activeNode.value.title}` : "等待进入学习路径"
));

const summaryDetail = computed(() => {
  if (!props.nodes.length) {
    return "系统还没有生成完整路径。完成课程选择和入学诊断后，这里会出现可执行的学习顺序。";
  }

  if (nextNode.value) {
    return `建议在完成当前节点后继续推进到“${nextNode.value.title}”，避免知识断层。`;
  }

  return "当前主要节点都已达标，接下来更适合做复盘和强化练习。";
});

const stats = computed(() => [
  {
    label: "已达标",
    value: `${completedCount.value}/${props.nodes.length || 0}`,
    detail: "达标节点会被系统视为稳定掌握",
  },
  {
    label: "当前节点",
    value: activeNode.value ? `${Math.round((activeNode.value.mastery ?? 0) * 100)}%` : "--",
    detail: activeNode.value ? "当前节点掌握度" : "等待选择节点",
  },
  {
    label: "下一建议",
    value: nextNode.value ? String(nextNode.value.order).padStart(2, "0") : "END",
    detail: nextNode.value ? nextNode.value.title : "当前路径已完成主线推进",
  },
]);

function isLocked(node) {
  return node.order > 1 && node.mastery < 0.2 && node.id !== props.currentNode;
}

function statusChipLabel(node) {
  if (node.id === props.currentNode) {
    return "当前";
  }
  if (node.mastery >= 0.65) {
    return "达标";
  }
  if (isLocked(node)) {
    return "待解锁";
  }
  return "建议";
}

function statusChipClass(node) {
  if (node.id === props.currentNode) {
    return "bg-secondary-soft text-secondary";
  }
  if (node.mastery >= 0.65) {
    return "bg-success-soft text-success";
  }
  if (isLocked(node)) {
    return "bg-space-surface/70 text-text-muted";
  }
  return "bg-primary-soft text-primary";
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
