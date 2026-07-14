<template>
  <header class="session-header">
    <div class="session-header__surface">
      <section class="session-header__course" aria-label="当前课程">
        <p class="session-header__label">课程</p>
        <CourseSwitcher
          :active-course="activeCourse"
          :enrolled-courses="enrolledCourses"
          @switch-course="$emit('switch-course', $event)"
          @browse-courses="$emit('browse-courses')"
        />
      </section>

      <section class="session-header__node" aria-label="当前节点">
        <p class="session-header__label">当前节点</p>
        <h1>{{ nodeTitle || "等待学习路径" }}</h1>
        <p class="session-header__course-title">{{ currentNodeCaption }}</p>
      </section>

      <section class="session-header__progress" aria-label="学习进度">
        <div class="session-header__progress-line">
          <p class="session-header__label">进度</p>
          <strong>{{ progressValue }}%</strong>
        </div>
        <progress :value="progressValue" max="100">{{ progressValue }}%</progress>
        <p>{{ masteredCount }}/{{ pathNodes.length || 0 }} 个节点已达标</p>
      </section>

      <div class="session-header__actions">
        <button
          type="button"
          class="session-header__primary session-header__desktop-action focus-ring"
          :aria-expanded="String(!tutorCollapsed)"
          aria-controls="workspace-coach-panel"
          @click="$emit('toggle-tutor')"
        >
          {{ tutorCollapsed ? "打开导师" : "收起导师" }}
        </button>

        <button
          type="button"
          class="session-header__mobile-primary focus-ring"
          aria-controls="workspace-learn-panel"
          @click="navigate('learn')"
        >
          继续
        </button>
      </div>
    </div>

    <p v-if="infoMessage" class="session-header__notice" role="status">
      {{ infoMessage }}
    </p>
  </header>
</template>

<script setup>
import { computed } from "vue";
import CourseSwitcher from "./CourseSwitcher.vue";

const props = defineProps({
  activeCourse: { type: Object, default: null },
  enrolledCourses: { type: Array, default: () => [] },
  nodeTitle: { type: String, default: "" },
  currentNode: { type: String, default: "" },
  pathNodes: { type: Array, default: () => [] },
  overallProgress: { type: Number, default: 0 },
  masteredCount: { type: Number, default: 0 },
  infoMessage: { type: String, default: "" },
  tutorCollapsed: { type: Boolean, default: false },
});

const emit = defineEmits([
  "switch-course",
  "browse-courses",
  "toggle-tutor",
  "navigate",
]);

const currentNodeMeta = computed(() => (
  props.pathNodes.find((node) => node.id === props.currentNode) ?? null
));

const currentNodeCaption = computed(() => {
  if (!props.pathNodes.length) return "路径生成后会显示学习节点";
  const order = Number(currentNodeMeta.value?.order ?? 0);
  return order > 0 ? `第 ${order} 个节点` : "当前学习位置";
});

const progressValue = computed(() => {
  const progress = Number(props.overallProgress);
  return Number.isFinite(progress) ? Math.max(0, Math.min(100, Math.round(progress))) : 0;
});

function navigate(key) {
  emit("navigate", key);
}
</script>

<style scoped>
.session-header {
  position: relative;
  z-index: var(--z-sticky);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--space-panel);
  padding: 0.8rem 1rem;
}

.session-header__surface {
  display: grid;
  grid-template-columns: minmax(11rem, 1.1fr) minmax(0, 1.7fr) minmax(10rem, 0.8fr) auto;
  align-items: center;
  gap: 1rem;
  margin: 0 auto;
  max-width: 1800px;
}

.session-header__course,
.session-header__node,
.session-header__progress {
  min-width: 0;
}

.session-header__label {
  margin: 0 0 0.35rem;
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 700;
  line-height: 1.2;
}

.session-header__node h1 {
  margin: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: var(--font-size-lg);
  font-weight: 750;
  letter-spacing: 0;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-header__course-title,
.session-header__progress p {
  margin: 0.3rem 0 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 0.72rem;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-header__progress-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}

.session-header__progress-line strong {
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
}

.session-header__progress progress {
  display: block;
  width: 100%;
  height: 0.35rem;
  overflow: hidden;
  border: 0;
  border-radius: var(--radius-pill);
  background: var(--border-subtle);
}

.session-header__progress progress::-webkit-progress-bar {
  background: var(--border-subtle);
}

.session-header__progress progress::-webkit-progress-value {
  background: var(--color-primary);
}

.session-header__progress progress::-moz-progress-bar {
  background: var(--color-primary);
}

.session-header__actions {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

.session-header__primary,
.session-header__mobile-primary {
  min-height: 2.75rem;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: var(--color-primary-text);
  font-size: 0.8rem;
  font-weight: 700;
  padding: 0.55rem 0.9rem;
  white-space: nowrap;
}

.session-header__primary:hover {
  background: var(--color-primary-dark);
}

.session-header__primary:active {
  transform: translateY(1px);
}

.session-header__mobile-primary {
  display: none;
}

.session-header__notice {
  margin: 0.65rem auto 0;
  max-width: 1800px;
  color: var(--text-secondary);
  font-size: 0.78rem;
  line-height: 1.45;
}

@media (max-width: 1279px) {
  .session-header {
    padding: 0.55rem 0.75rem;
  }

  .session-header__surface {
    grid-template-columns: minmax(6rem, 1fr) minmax(4.5rem, 1fr) 2.75rem auto;
    gap: 0.45rem;
  }

  .session-header__label,
  .session-header__course-title,
  .session-header__progress progress,
  .session-header__progress > p,
  .session-header__desktop-action {
    display: none;
  }

  .session-header__course,
  .session-header__node,
  .session-header__progress,
  .session-header__actions {
    grid-column: auto;
    min-width: 0;
  }

  .session-header__course :deep(.course-switcher__trigger) {
    grid-template-columns: minmax(0, 1fr) auto;
    width: 100%;
    padding: 0.45rem 0.55rem;
  }

  .session-header__course :deep(.course-switcher__icon) {
    display: none;
  }

  .session-header__node h1 {
    font-size: 0.85rem;
  }

  .session-header__progress {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .session-header__progress-line {
    display: block;
  }

  .session-header__progress-line strong {
    font-size: 0.75rem;
  }

  .session-header__actions {
    justify-content: stretch;
  }

  .session-header__mobile-primary {
    display: inline-flex;
    min-width: 2.9rem;
    align-items: center;
    justify-content: center;
    padding-inline: 0.65rem;
  }
}

@media (max-width: 359px) {
  .session-header__surface {
    grid-template-columns: minmax(5.25rem, 1fr) minmax(4rem, 0.9fr) 2.5rem auto;
    gap: 0.3rem;
  }

  .session-header__mobile-primary {
    min-width: 2.75rem;
    padding-inline: 0.45rem;
  }
}
</style>
