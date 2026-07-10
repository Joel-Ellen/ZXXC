<template>
  <header class="session-header">
    <div class="session-header__surface">
      <div class="session-header__brand lg:hidden" aria-hidden="true">
        <span class="session-header__mark">EA</span>
        <span class="session-header__brand-copy">
          <strong>EduAgent</strong>
          <span>学习工作台</span>
        </span>
      </div>

      <div class="session-header__grid" aria-label="当前学习会话">
        <section class="session-header__group session-header__group--course" aria-label="课程">
          <p class="session-header__label">课程</p>
          <CourseSwitcher
            :active-course="activeCourse"
            :enrolled-courses="enrolledCourses"
            @switch-course="$emit('switch-course', $event)"
            @browse-courses="$emit('browse-courses')"
          />
          <p class="session-header__user">{{ userLabel }}</p>
        </section>

        <section class="session-header__group" aria-label="当前节点">
          <div class="session-header__line">
            <p class="session-header__label">{{ stageLabel }}</p>
            <span class="session-header__pill">{{ currentNodeCaption }}</span>
          </div>
          <h1 class="session-header__title">{{ nodeTitle || "等待生成学习路径" }}</h1>
          <p class="session-header__subtle">{{ activeCourse?.title_cn || "课程工作台" }}</p>
        </section>

        <section class="session-header__group" aria-label="下一步">
          <p class="session-header__label">下一步</p>
          <h2 class="session-header__next">{{ nextStepTitle }}</h2>
          <p class="session-header__subtle">{{ nextStepDetail }}</p>
        </section>

        <section class="session-header__group session-header__group--progress" aria-label="学习进度">
          <div class="session-header__line">
            <p class="session-header__label">进度</p>
            <span class="session-header__meter-value">{{ progressValue }}%</span>
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
        <nav
          v-if="navigation.length"
          class="session-header__nav hidden xl:flex"
          aria-label="工作台主导航"
        >
          <button
            v-for="item in navigation"
            :key="item.key"
            type="button"
            class="session-header__nav-button focus-ring"
            :class="{ 'is-active': item.active }"
            :aria-controls="item.targetId"
            :aria-expanded="item.expanded"
            :aria-haspopup="item.hasPopup ? 'dialog' : undefined"
            :aria-pressed="String(item.active)"
            @click="$emit('navigate', item.key)"
          >
            {{ item.label }}
          </button>
        </nav>

        <div class="session-header__account">
          <button
            type="button"
            class="session-header__utility focus-ring"
            @click="$emit('go-home')"
          >
            首页
          </button>
          <button
            type="button"
            class="session-header__utility session-header__utility--danger focus-ring"
            @click="$emit('logout')"
          >
            退出
          </button>
        </div>
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

const currentNodeMeta = computed(() =>
  props.pathNodes.find((node) => node.id === props.currentNode) ?? null,
);

const nextNode = computed(() => {
  const currentIndex = props.pathNodes.findIndex((node) => node.id === props.currentNode);
  if (currentIndex < 0) {
    return props.pathNodes.find((node) => node.mastery < 0.65) ?? null;
  }

  return props.pathNodes.slice(currentIndex + 1).find((node) => node.mastery < 0.65) ?? null;
});

const currentMastery = computed(() =>
  Math.round((currentNodeMeta.value?.mastery ?? 0) * 100),
);

const progressValue = computed(() => {
  const progress = Number.isFinite(props.overallProgress) ? props.overallProgress : 0;
  return Math.max(0, Math.min(100, Math.round(progress)));
});

const userLabel = computed(() =>
  props.user?.display_name || props.user?.user_id || "未登录",
);

const stageLabel = computed(() => {
  if (props.bootMode === "probe") return "入学诊断";
  if (props.isLoadingNode) return "资源生成中";
  if (props.isBusy) return "同步中";
  if (!props.pathNodes.length) return "路径待生成";
  if (currentMastery.value >= 65) return "节点已达标";
  return "继续学习";
});

const currentNodeCaption = computed(() => {
  if (!props.pathNodes.length) return "等待路径";

  const order = currentNodeMeta.value?.order ?? 0;
  return order ? `${order}/${props.pathNodes.length}` : "当前节点";
});

const nextStepTitle = computed(() => {
  if (props.bootMode === "probe") return "完成入学诊断";
  if (props.isLoadingNode) return "等待资源装配完成";
  if (!props.pathNodes.length) return "生成学习路径";
  if (!props.cards.length) return "装配当前节点资源";
  if (currentMastery.value < 65) return "完成当前节点学习";
  return nextNode.value ? `切换到 ${nextNode.value.title}` : "进入复盘与串联";
});

const nextStepDetail = computed(() => {
  if (props.bootMode === "probe") {
    return "诊断会决定起点、资源密度和后续节点顺序。";
  }

  if (props.isLoadingNode) {
    return "先保持当前节点，等待概念、代码、练习和诊断内容到位。";
  }

  if (!props.pathNodes.length) {
    return "路径生成后，工作台会自动定位第一个建议节点。";
  }

  if (!props.cards.length) {
    return "当前节点还没有可展开材料，优先触发资源生成。";
  }

  if (currentMastery.value < 65) {
    return "建议按概念、代码、练习、诊断的顺序推进。";
  }

  return nextNode.value
    ? "当前节点接近达标，可以准备进入下一个薄弱点。"
    : "主线薄弱点已覆盖，适合做复盘和面试化练习。";
});
</script>

<style scoped>
.session-header {
  position: relative;
  z-index: var(--z-sticky);
  padding: 0.75rem 1rem 0.65rem;
}

.session-header__surface {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: stretch;
  gap: 0.75rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--space-panel);
  box-shadow: var(--workspace-shadow-soft);
  padding: 0.55rem;
}

.session-header__brand {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  grid-column: 1 / -1;
  min-width: 0;
  padding: 0.2rem 0.25rem;
}

.session-header__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border: 1px solid color-mix(in srgb, var(--color-primary) 22%, var(--border-subtle));
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
  font-size: 0.82rem;
  font-weight: 900;
}

.session-header__brand-copy {
  display: grid;
  min-width: 0;
  gap: 0.1rem;
}

.session-header__brand-copy strong,
.session-header__brand-copy span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-header__brand-copy strong {
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  line-height: 1.15;
}

.session-header__brand-copy span {
  color: var(--text-muted);
  font-size: 0.72rem;
}

.session-header__grid {
  display: grid;
  min-width: 0;
  grid-template-columns:
    minmax(14rem, 1.1fr)
    minmax(13rem, 1fr)
    minmax(15rem, 1.18fr)
    minmax(11rem, 0.82fr);
}

.session-header__group {
  display: flex;
  min-width: 0;
  min-height: 5.6rem;
  flex-direction: column;
  justify-content: center;
  gap: 0.45rem;
  padding: 0.65rem 0.9rem;
}

.session-header__group + .session-header__group {
  border-left: 1px solid var(--border-subtle);
}

.session-header__group--course {
  align-items: flex-start;
}

.session-header__group--progress {
  min-width: 11rem;
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
  font-size: 0.68rem;
  font-weight: 700;
}

.session-header__meter-value {
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  font-weight: 800;
}

.session-header__meter {
  height: 0.45rem;
  overflow: hidden;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--border-subtle) 72%, transparent);
}

.session-header__meter span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--color-primary);
  transition: width var(--duration-slow) var(--ease-emphasized);
}

.session-header__tools {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.session-header__nav {
  align-items: center;
  gap: 0.25rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--space-elevated);
  padding: 0.3rem;
}

.session-header__nav-button,
.session-header__utility {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 800;
  line-height: 1;
  transition:
    background var(--duration-fast) var(--ease-standard),
    border-color var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard);
}

.session-header__nav-button {
  border-radius: var(--radius-pill);
  padding: 0.6rem 0.75rem;
}

.session-header__nav-button:hover,
.session-header__nav-button.is-active {
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
}

.session-header__account {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.session-header__utility {
  min-height: 2.3rem;
  border-color: var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--space-elevated);
  padding: 0.55rem 0.75rem;
}

.session-header__utility:hover {
  border-color: color-mix(in srgb, var(--color-primary) 26%, var(--border-strong));
  color: var(--text-primary);
}

.session-header__utility--danger:hover {
  border-color: color-mix(in srgb, var(--color-error) 32%, var(--border-strong));
  color: var(--color-error);
}

.session-header__notice {
  margin: 0.45rem 0 0;
  border: 1px solid color-mix(in srgb, var(--color-primary) 18%, var(--border-subtle));
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
  padding: 0.55rem 0.8rem;
  font-size: 0.78rem;
  font-weight: 650;
  line-height: 1.45;
}

@media (max-width: 1439px) {
  .session-header__surface {
    grid-template-columns: minmax(0, 1fr);
  }

  .session-header__tools {
    justify-content: flex-end;
  }
}

@media (min-width: 1024px) {
  .session-header__brand {
    display: none;
  }
}

@media (max-width: 1279px) {
  .session-header__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .session-header__group:nth-child(odd) {
    border-left: 0;
  }

  .session-header__group:nth-child(n + 3) {
    border-top: 1px solid var(--border-subtle);
  }
}

@media (max-width: 767px) {
  .session-header {
    padding: 0.65rem;
  }

  .session-header__grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .session-header__group,
  .session-header__group + .session-header__group {
    min-height: auto;
    border-left: 0;
    border-top: 1px solid var(--border-subtle);
    padding: 0.7rem 0.55rem;
  }

  .session-header__group:first-child {
    border-top: 0;
  }

  .session-header__account {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
