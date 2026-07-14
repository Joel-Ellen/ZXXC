<template>
  <aside class="course-path-panel hidden h-full shrink-0 xl:flex" aria-label="课程路径">
    <div class="course-path-panel__inner">
      <div class="course-path-panel__heading">
        <div>
          <p class="course-path-panel__eyebrow">课程路径</p>
          <h2>学习节点</h2>
        </div>
        <span class="course-path-panel__count">{{ completedCount }}/{{ pathNodes.length }}</span>
      </div>

      <nav class="course-path-panel__list" aria-label="学习节点列表">
        <button
          v-for="(node, index) in pathNodes"
          :key="node.id"
          type="button"
          class="course-path-panel__node focus-ring"
          :class="nodeClass(node)"
          :aria-current="node.id === currentNode ? 'step' : undefined"
          @click="$emit('select-node', node.id)"
        >
          <span class="course-path-panel__order">{{ nodeOrder(node, index) }}</span>
          <span class="course-path-panel__node-copy">
            <span class="course-path-panel__node-title">{{ node.title }}</span>
            <span class="course-path-panel__node-state">{{ nodeState(node) }}</span>
          </span>
          <span class="course-path-panel__mastery">{{ mastery(node) }}%</span>
        </button>

        <p v-if="!pathNodes.length" class="course-path-panel__empty">
          完成诊断后，学习路径会显示在这里。
        </p>
      </nav>

      <div class="course-path-panel__footer">
        <span>当前进度</span>
        <strong>{{ currentNodeLabel }}</strong>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  pathNodes: { type: Array, default: () => [] },
  currentNode: { type: String, default: "" },
});

defineEmits(["select-node"]);

const completedCount = computed(() => (
  props.pathNodes.filter((node) => Number(node?.mastery ?? 0) >= 0.65).length
));

const currentNodeLabel = computed(() => {
  const node = props.pathNodes.find((candidate) => candidate.id === props.currentNode);
  return node?.title || "等待选择节点";
});

function mastery(node) {
  return Math.max(0, Math.min(100, Math.round(Number(node?.mastery ?? 0) * 100)));
}

function nodeOrder(node, index) {
  const order = Number(node?.order);
  return String(Number.isFinite(order) && order > 0 ? order : index + 1).padStart(2, "0");
}

function nodeState(node) {
  if (node?.id === props.currentNode) return "当前学习";
  if (mastery(node) >= 65) return "已完成";
  return "待学习";
}

function nodeClass(node) {
  if (node?.id === props.currentNode) return "is-current";
  if (mastery(node) >= 65) return "is-complete";
  return "";
}
</script>

<style scoped>
.course-path-panel {
  width: 20%;
  flex: 0 0 20%;
  border-right: 1px solid var(--border-subtle);
  background: var(--space-elevated);
}

.course-path-panel__inner {
  display: flex;
  min-height: 0;
  width: 100%;
  flex-direction: column;
  padding: 1.25rem 1rem 1rem;
}

.course-path-panel__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0 0.25rem 1rem;
}

.course-path-panel__eyebrow {
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 700;
  line-height: 1.2;
}

.course-path-panel__heading h2 {
  margin: 0.3rem 0 0;
  color: var(--text-primary);
  font-size: var(--font-size-lg);
  font-weight: 750;
  line-height: 1.25;
}

.course-path-panel__count,
.course-path-panel__mastery {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
}

.course-path-panel__count {
  padding-top: 0.15rem;
}

.course-path-panel__list {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 0.3rem;
  overflow-y: auto;
  padding-right: 0.2rem;
}

.course-path-panel__node {
  display: grid;
  grid-template-columns: 2.1rem minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.55rem;
  width: 100%;
  min-height: 3.75rem;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  padding: 0.6rem 0.55rem;
  text-align: left;
  transition: background-color var(--duration-fast) var(--ease-standard), border-color var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);
}

.course-path-panel__node:hover {
  background: var(--card-bg-hover);
  color: var(--text-primary);
}

.course-path-panel__node.is-current {
  border-color: color-mix(in srgb, var(--color-primary) 26%, var(--border-subtle));
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
}

.course-path-panel__node.is-complete:not(.is-current) .course-path-panel__node-state,
.course-path-panel__node.is-complete:not(.is-current) .course-path-panel__mastery {
  color: var(--color-success-dark);
}

.course-path-panel__order {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-variant-numeric: tabular-nums;
}

.course-path-panel__node-copy {
  display: grid;
  min-width: 0;
  gap: 0.2rem;
}

.course-path-panel__node-title,
.course-path-panel__node-state {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.course-path-panel__node-title {
  color: var(--text-primary);
  font-size: 0.82rem;
  font-weight: 650;
  line-height: 1.25;
}

.course-path-panel__node-state {
  color: var(--text-muted);
  font-size: 0.7rem;
  line-height: 1.2;
}

.course-path-panel__empty {
  margin: 1rem 0.25rem;
  color: var(--text-muted);
  font-size: 0.82rem;
  line-height: 1.6;
}

.course-path-panel__footer {
  display: grid;
  gap: 0.35rem;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-muted);
  font-size: 0.72rem;
  margin-top: 0.85rem;
  padding: 0.9rem 0.25rem 0;
}

.course-path-panel__footer strong {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 0.78rem;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
