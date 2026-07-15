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
  navigation: { type: Array, default: () => [] },
});

defineEmits([
  "switch-course",
  "browse-courses",
  "go-home",
  "logout",
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
</script>

<style scoped>
.session-header {
  position: relative;
  z-index: var(--z-sticky);
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
  font-size: 0.68rem;
}

.session-header__course {
  min-width: 9.5rem;
}

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

  .session-header__course,
  .session-header__user {
    display: none;
  }

  .session-header__nav {
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

  .session-header__nav::-webkit-scrollbar {
    display: none;
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
