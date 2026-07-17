<template>
  <header class="session-header">
    <div class="session-header__brand-group">
      <button type="button" class="session-header__brand focus-ring" aria-label="返回首页" @click="$emit('go-home')">
        <span class="session-header__mark">EA</span>
        <span class="session-header__brand-copy">
          <strong>EduAgent</strong>
          <small>智能学习工作台</small>
        </span>
      </button>

      <CourseSwitcher
        class="session-header__course"
        :active-course="activeCourse"
        :enrolled-courses="enrolledCourses"
        @switch-course="$emit('switch-course', $event)"
        @browse-courses="$emit('browse-courses')"
      />
    </div>

<<<<<<< HEAD
    <nav class="session-header__nav" aria-label="工作台主导航">
      <button
        v-for="item in navigation"
        :key="item.key"
        type="button"
        class="session-header__nav-button focus-ring"
        :class="{ 'is-active': item.active }"
        :aria-controls="item.targetId"
        :aria-current="item.active && !item.hasPopup ? 'page' : undefined"
        :aria-expanded="item.expanded"
        :aria-haspopup="item.hasPopup ? 'dialog' : undefined"
        @click="$emit('navigate', item.key)"
      >
        {{ item.label }}
      </button>
    </nav>

    <div class="session-header__session">
      <div class="session-header__node">
        <span>{{ stageLabel }}</span>
        <strong>{{ nodeTitle || "等待生成学习路径" }}</strong>
      </div>
      <div class="session-header__progress" :aria-label="`整体学习进度 ${progressValue}%`">
        <strong>{{ progressValue }}%</strong>
        <span>{{ masteredCount }}/{{ pathNodes.length || 0 }} 节点</span>
=======
          <section class="session-header__group session-header__node" aria-label="当前节点">
            <div class="session-header__line">
              <p class="session-header__label">{{ stageLabel }}</p>
              <span class="session-header__pill">{{ currentNodeCaption }}</span>
            </div>
            <h1 class="session-header__title" aria-hidden="true">{{ nodeTitle || "等待生成学习路径" }}</h1>
            <p class="session-header__subtle">{{ activeCourse?.title_cn || "课程工作台" }}</p>
          </section>

          <section class="session-header__group" aria-label="下一步">
            <p class="session-header__label">下一步</p>
            <h2 class="session-header__next">{{ nextStepTitle }}</h2>
            <p class="session-header__subtle">{{ nextStepDetail }}</p>
          </section>

          <section class="session-header__group session-header__group--progress session-header__progress" aria-label="学习进度">
            <div class="session-header__line">
              <p class="session-header__label">进度</p>
              <strong class="session-header__meter-value">{{ progressValue }}%</strong>
            </div>
            <div class="session-header__meter" aria-hidden="true">
              <span :style="{ width: `${progressValue}%` }" />
            </div>
            <p class="session-header__subtle">
              {{ masteredCount }}/{{ pathNodes.length || 0 }} 节点达标 · 当前 {{ currentMastery }}%
            </p>
          </section>
        </div>

        <div class="session-header__tools">
          <button
            type="button"
            class="session-header__action session-header__action--desktop session-header__primary focus-ring"
            :aria-expanded="String(!tutorCollapsed)"
            aria-controls="workspace-coach-panel"
            @click="$emit('toggle-tutor')"
          >
            {{ tutorCollapsed ? "打开导师" : "收起导师" }}
          </button>
          <button
            type="button"
            class="session-header__action session-header__action--mobile session-header__mobile-primary focus-ring"
            aria-controls="workspace-learn-panel"
            @click="navigate('learn')"
          >
            继续学习
          </button>
        </div>

        <p v-if="infoMessage" class="session-header__notice" role="status">
          {{ infoMessage }}
        </p>
>>>>>>> origin/main
      </div>
    </div>

    <div class="session-header__tools">
      <button
        type="button"
        class="session-header__icon-button focus-ring"
        title="显示设置"
        aria-label="显示设置"
        @click="$emit('navigate', 'settings')"
      >
        <IconSettings :size="18" />
      </button>
      <button
        type="button"
        class="session-header__icon-button focus-ring"
        title="重新测评"
        aria-label="重新测评"
        @click="$emit('navigate', 'probe')"
      >
        <IconQuiz :size="18" />
      </button>
      <span class="session-header__user">{{ userLabel }}</span>
      <button type="button" class="session-header__logout focus-ring" @click="$emit('logout')">
        退出
      </button>
    </div>

    <p v-if="infoMessage" class="session-header__notice" role="status">
      {{ infoMessage }}
    </p>
  </header>
</template>

<script setup>
import { computed } from "vue";
import IconQuiz from "../icons/IconQuiz.vue";
import IconSettings from "../icons/IconSettings.vue";
import CourseSwitcher from "./CourseSwitcher.vue";

const props = defineProps({
  user: { type: Object, default: null },
  activeCourse: { type: Object, default: null },
  enrolledCourses: { type: Array, default: () => [] },
  bootMode: { type: String, default: "loading" },
  nodeTitle: { type: String, default: "" },
  currentNode: { type: String, default: "" },
  pathNodes: { type: Array, default: () => [] },
  cards: { type: Array, default: () => [] },
  overallProgress: { type: Number, default: 0 },
  masteredCount: { type: Number, default: 0 },
  infoMessage: { type: String, default: "" },
  isBusy: { type: Boolean, default: false },
  isLoadingNode: { type: Boolean, default: false },
  tutorCollapsed: { type: Boolean, default: false },
});

const emit = defineEmits([
  "switch-course",
  "browse-courses",
  "toggle-tutor",
  "navigate",
]);

const progressValue = computed(() => {
  const value = Number.isFinite(props.overallProgress) ? props.overallProgress : 0;
  return Math.max(0, Math.min(100, Math.round(value)));
});

const userLabel = computed(() => props.user?.display_name || props.user?.user_id || "学习者");

const stageLabel = computed(() => {
  if (props.bootMode === "probe") return "入学诊断";
  if (props.isLoadingNode) return "资源生成中";
  if (props.isBusy) return "状态同步中";
  if (!props.pathNodes.length) return "路径待生成";
  if (!props.cards.length) return "资源待装配";
  return "当前学习节点";
});

function navigate(key) {
  emit("navigate", key);
}
</script>

<style scoped>
.session-header {
  position: relative;
  z-index: var(--z-sticky);
<<<<<<< HEAD
=======
  pointer-events: none;
}

.session-header__panel {
  position: absolute;
  top: 3rem;
  right: 0.75rem;
  left: 0.75rem;
  pointer-events: auto;
  transform: translateY(calc(-100% - 0.5rem));
  visibility: hidden;
  transition:
    transform var(--duration-slow) var(--ease-emphasized),
    visibility 0s linear var(--duration-slow);
}

.session-header:hover .session-header__panel,
.session-header:focus-within .session-header__panel {
  transform: translateY(0);
  visibility: visible;
  transition-delay: 0s;
}

.session-header__peek {
  position: absolute;
  top: 0;
  right: 0.75rem;
  left: 0.75rem;
  display: flex;
  height: 3rem;
  align-items: center;
  justify-content: center;
  gap: 0.65rem;
  border: 0;
  border-bottom: 1px solid color-mix(in srgb, var(--color-primary) 18%, var(--border-subtle));
  background: color-mix(in srgb, var(--space-panel) 84%, transparent);
  color: var(--color-primary-dark);
  backdrop-filter: blur(8px);
  pointer-events: auto;
  padding: 0;
  transition:
    background var(--duration-fast) var(--ease-standard);
}

.session-header__peek-line {
  display: block;
  width: 2.5rem;
  height: 0.25rem;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--color-primary) 68%, var(--border-strong));
  opacity: 1;
  transition: opacity var(--duration-base) var(--ease-standard);
}

.session-header__peek-label {
  font-size: var(--workspace-font-12, 0.75rem);
  font-weight: 750;
  line-height: 1;
  opacity: 1;
  transform: translateY(0);
  transition:
    opacity var(--duration-base) var(--ease-standard),
    transform var(--duration-base) var(--ease-standard);
}

.session-header__peek:hover,
.session-header__peek:focus-visible {
  background: color-mix(in srgb, var(--color-primary-soft) 90%, var(--space-panel));
}

.session-header:hover .session-header__peek {
  background: var(--space-panel);
}

.session-header:hover .session-header__peek-label,
.session-header:focus-within .session-header__peek-label {
  opacity: 0;
  transform: translateY(-0.3rem);
}

.session-header:hover .session-header__peek-line,
.session-header:focus-within .session-header__peek-line {
  opacity: 0;
}

.session-header__surface {
>>>>>>> origin/main
  display: grid;
  min-height: 4.75rem;
  grid-template-columns: auto minmax(26rem, 1fr) auto auto;
  align-items: center;
  gap: 1rem;
  border-bottom: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--space-panel) 96%, transparent);
  padding: 0.65rem 1rem;
  backdrop-filter: blur(18px);
}

.session-header__brand-group,
.session-header__brand,
.session-header__tools,
.session-header__session,
.session-header__nav {
  display: flex;
  align-items: center;
}

.session-header__brand-group {
  gap: 0.75rem;
}

.session-header__brand {
  gap: 0.65rem;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  padding: 0;
  text-align: left;
}

.session-header__mark {
  display: grid;
  width: 2.6rem;
  aspect-ratio: 1;
  place-items: center;
  border-radius: var(--radius-sm);
  background: var(--text-primary);
  color: var(--space-bg);
  font-size: 0.8rem;
  font-weight: 900;
  letter-spacing: 0.08em;
}

.session-header__brand-copy {
  display: grid;
  gap: 0.08rem;
  white-space: nowrap;
}

.session-header__brand-copy strong {
  font-size: 0.92rem;
  line-height: 1.1;
}

.session-header__brand-copy small {
  color: var(--text-muted);
<<<<<<< HEAD
=======
  font-size: 0.72rem;
}

.session-header__grid {
  display: grid;
  min-width: 0;
  grid-template-columns:
    minmax(12rem, 1.05fr)
    minmax(12rem, 1fr)
    minmax(13rem, 1.08fr)
    minmax(9rem, 0.78fr);
}

.session-header__group {
  display: flex;
  min-width: 0;
  min-height: 4.25rem;
  flex-direction: column;
  justify-content: center;
  gap: 0.25rem;
  padding: 0.35rem 0.75rem;
}

.session-header__group + .session-header__group {
  border-left: 1px solid var(--border-subtle);
}

.session-header__group--course {
  align-items: flex-start;
}

.session-header__group--progress {
  min-width: 9rem;
}

.session-header__group--course :deep(.course-switcher__trigger) {
  min-height: 2.75rem;
  padding-block: 0.3rem;
}

.session-header__line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
  gap: 0.65rem;
}

.session-header__label {
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 800;
  line-height: 1.2;
}

.session-header__title,
.session-header__next {
  margin: 0;
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font-size: var(--font-size-md);
  font-weight: 850;
  letter-spacing: 0;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-header__next {
  font-size: var(--font-size-sm);
}

.session-header__subtle,
.session-header__user {
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 0.76rem;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-header__user {
  max-width: 100%;
  padding-left: 0.1rem;
}

.session-header__pill {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--space-elevated);
  color: var(--text-secondary);
  padding: 0.15rem 0.5rem;
  font-family: var(--font-mono);
>>>>>>> origin/main
  font-size: 0.68rem;
}

.session-header__course {
  min-width: 9.5rem;
}

<<<<<<< HEAD
.session-header__nav {
  justify-content: center;
  gap: 0.2rem;
  white-space: nowrap;
}

.session-header__nav-button {
  min-height: 2.45rem;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  padding: 0.6rem 0.8rem;
  font-size: 0.78rem;
  font-weight: 750;
  transition: background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard), transform var(--duration-fast) var(--ease-emphasized);
}

.session-header__nav-button:hover {
  background: var(--space-elevated);
  color: var(--text-primary);
}

.session-header__nav-button.is-active {
  background: var(--text-primary);
  color: var(--space-bg);
}

.session-header__nav-button:active,
.session-header__icon-button:active,
.session-header__logout:active {
  transform: scale(0.97);
}

.session-header__session {
  min-width: 14rem;
  gap: 0.8rem;
  border-left: 1px solid var(--border-subtle);
  padding-left: 1rem;
}

.session-header__node {
  display: grid;
  min-width: 0;
  gap: 0.14rem;
}

.session-header__node span,
.session-header__progress span {
  color: var(--text-muted);
  font-size: 0.67rem;
}

.session-header__node strong {
  max-width: 9rem;
  overflow: hidden;
  font-size: 0.78rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-header__progress {
  display: grid;
  flex-shrink: 0;
  gap: 0.08rem;
  text-align: right;
}

.session-header__progress strong {
  font-family: var(--font-mono);
  font-size: 0.9rem;
}

.session-header__tools {
  gap: 0.35rem;
}

.session-header__icon-button,
.session-header__logout {
  display: grid;
  min-height: 2.45rem;
  place-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  transition: border-color var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard), transform var(--duration-fast) var(--ease-emphasized);
}

.session-header__icon-button {
  width: 2.45rem;
  padding: 0;
}

.session-header__logout {
  padding: 0.55rem 0.75rem;
  font-size: 0.76rem;
  font-weight: 750;
}

.session-header__icon-button:hover,
.session-header__logout:hover {
  border-color: var(--border-strong);
  color: var(--text-primary);
}

.session-header__user {
  max-width: 6rem;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 0.74rem;
  text-overflow: ellipsis;
  white-space: nowrap;
=======
.session-header__action {
  min-height: 2.75rem;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: var(--color-primary-text);
  padding: 0.55rem 0.75rem;
  font-size: 0.72rem;
  font-weight: 800;
  line-height: 1;
  white-space: nowrap;
  transition: background var(--duration-fast) var(--ease-standard);
}

.session-header__action:hover {
  background: var(--color-primary-dark);
}

.session-header__action--mobile {
  display: none;
>>>>>>> origin/main
}

.session-header__notice {
  position: absolute;
  top: calc(100% + 0.5rem);
  right: 1rem;
  max-width: min(28rem, calc(100vw - 2rem));
  margin: 0;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--space-panel);
  box-shadow: var(--shadow-md);
  padding: 0.75rem 1rem;
  color: var(--text-secondary);
  font-size: 0.78rem;
}

@media (max-width: 1280px) {
  .session-header {
    grid-template-columns: auto minmax(22rem, 1fr) auto;
  }

  .session-header__session,
  .session-header__brand-copy small {
    display: none;
  }
}

@media (max-width: 980px) {
  .session-header {
    width: 100%;
    max-width: 100vw;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 0.55rem;
    overflow: hidden;
  }

<<<<<<< HEAD
  .session-header__course,
=======
  .session-header__brand {
    display: none;
  }

  .session-header__grid {
    grid-template-columns: minmax(11rem, 1fr) minmax(12rem, 1fr) minmax(9rem, 0.8fr);
  }

  .session-header__group:nth-child(3) {
    display: none;
  }

  .session-header__group:nth-child(4) {
    border-left: 1px solid var(--border-subtle);
  }
}

@media (min-width: 1280px) {
  .session-header__panel,
  .session-header__peek {
    left: calc(96px + 0.75rem);
  }
}

@media (min-width: 1280px) {
  .session-header__brand {
    display: none;
  }

>>>>>>> origin/main
  .session-header__user {
    display: none;
  }

<<<<<<< HEAD
  .session-header__nav {
=======
@media (max-width: 767px) {
  .session-header {
    position: relative;
    height: auto;
    pointer-events: auto;
    padding: max(0.5rem, env(safe-area-inset-top, 0px)) 0.5rem 0.4rem;
  }

  .session-header__panel {
    position: relative;
    top: auto;
    right: auto;
    left: auto;
    transform: none;
    visibility: visible;
  }

  .session-header__peek {
    display: none;
  }

  .session-header__surface {
    grid-template-columns: minmax(0, 1fr);
    gap: 0.35rem;
    padding: 0.4rem;
  }

  .session-header__brand {
    display: flex;
    padding: 0.1rem;
  }

  .session-header__mark {
    width: 2.25rem;
    height: 2.25rem;
  }

  .session-header__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .session-header__group,
  .session-header__group + .session-header__group {
    min-height: auto;
    border-left: 0;
    border-top: 1px solid var(--border-subtle);
    padding: 0.55rem 0.5rem;
  }

  .session-header__group:nth-child(odd) {
    border-left: 0;
  }

  .session-header__group:nth-child(even) {
    border-left: 1px solid var(--border-subtle);
  }

  .session-header__group:nth-child(-n + 2) {
    border-top: 0;
  }

  .session-header__group--course,
  .session-header__group:nth-child(2) {
>>>>>>> origin/main
    grid-column: 1 / -1;
    grid-row: 2;
    justify-content: flex-start;
    overflow-x: auto;
    padding-top: 0.15rem;
    scrollbar-width: none;
  }

  .session-header__tools {
    grid-column: 2;
    grid-row: 1;
    justify-self: end;
  }

<<<<<<< HEAD
  .session-header__nav::-webkit-scrollbar {
    display: none;
=======
  .session-header__action--desktop {
    display: none;
  }

  .session-header__action--mobile {
    display: inline-flex;
    align-items: center;
    justify-content: center;
>>>>>>> origin/main
  }
}

@media (max-width: 520px) {
  .session-header {
    padding: max(0.55rem, env(safe-area-inset-top, 0px)) 0.65rem 0.45rem;
  }

  .session-header__brand-copy,
  .session-header__logout {
    display: none;
  }

  .session-header__tools {
    position: absolute;
    top: max(0.55rem, env(safe-area-inset-top, 0px));
    right: 0.65rem;
    display: flex;
  }

  .session-header__nav-button {
    min-height: 2.3rem;
    padding-inline: 0.65rem;
  }
}
</style>
