<template>
  <div class="course-page">
    <header class="course-topbar">
      <div class="course-topbar__inner">
        <button type="button" class="course-brand focus-ring" aria-label="返回首页" @click="$emit('go-home')">
          <span class="course-brand__mark" aria-hidden="true">EA</span>
          <span class="course-brand__copy">
            <strong>EduAgent</strong>
            <small>课程中心</small>
          </span>
        </button>

        <button
          type="button"
          class="course-return focus-ring"
          @click="activeCourse ? $emit('back') : $emit('go-home')"
        >
          {{ activeCourse ? "返回工作台" : "返回首页" }}
        </button>
      </div>
    </header>

    <main class="course-main">
      <section class="course-heading" aria-labelledby="course-page-title">
        <div>
          <h1 id="course-page-title">{{ activeCourse ? "选择其他课程" : "选择一门课程" }}</h1>
          <p>
            {{ activeCourse
              ? "课程之间的学习进度相互独立，切换后会进入对应的学习工作台。"
              : "选择后先完成简短诊断，系统会生成适合你的学习路径。" }}
          </p>
        </div>

        <div class="course-search">
          <label for="course-search-input">搜索课程</label>
          <input
            id="course-search-input"
            v-model="searchQuery"
            type="search"
            autocomplete="off"
            placeholder="搜索课程名称或知识方向"
            class="focus-ring"
            @input="onSearchInput"
          />
        </div>
      </section>

      <div class="course-list-heading">
        <h2>课程列表</h2>
        <span>{{ filteredCourses.length }} 门课程</span>
      </div>

      <div v-if="loading && !courses.length" class="course-grid" aria-label="正在加载课程">
        <div v-for="item in 5" :key="item" class="course-skeleton" aria-hidden="true">
          <div class="course-skeleton__code" />
          <div class="course-skeleton__title" />
          <div class="course-skeleton__line" />
          <div class="course-skeleton__line is-short" />
          <div class="course-skeleton__meta" />
          <div class="course-skeleton__action" />
        </div>
      </div>

      <section v-else-if="!filteredCourses.length" class="course-empty-state">
        <h2>没有找到匹配的课程</h2>
        <p>换一个关键词试试。</p>
        <button type="button" class="focus-ring" @click="resetSearch">查看全部课程</button>
      </section>

      <section v-else class="course-grid" aria-label="可选课程">
        <article
          v-for="(course, index) in filteredCourses"
          :key="course.course_id"
          class="course-card"
          :class="{ 'is-current': course.course_id === activeCourse?.course_id }"
          :style="{ '--course-index': Math.min(index, 6) }"
        >
          <div class="course-card__header">
            <div class="course-card__code" aria-hidden="true">{{ courseCode(course) }}</div>
            <span class="course-card__status" :class="statusClass(course)">{{ statusLabel(course) }}</span>
          </div>

          <h2>{{ course.title_cn }}</h2>
          <p class="course-card__description">{{ course.description_cn }}</p>

          <dl class="course-card__facts" aria-label="课程信息">
            <div>
              <dt>难度</dt>
              <dd>{{ difficultyLabel(course.difficulty) }}</dd>
            </div>
            <div>
              <dt>学时</dt>
              <dd>{{ formatHours(course.estimated_hours) }}</dd>
            </div>
            <div>
              <dt>结构</dt>
              <dd>{{ nodeLabel(course.node_count) }}</dd>
            </div>
          </dl>

          <p class="course-card__prerequisite">{{ prerequisiteLabel(course) || "无需前置课程" }}</p>

          <button
            type="button"
            class="course-card__action focus-ring"
            :disabled="loading || enrolling === course.course_id"
            @click="selectCourse(course)"
          >
            {{ enrolling === course.course_id ? "正在准备" : actionLabel(course) }}
          </button>
        </article>
      </section>

      <p class="sr-only" role="status" aria-live="polite">
        {{ enrolling ? "正在准备所选课程" : "" }}
      </p>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps({
  courses: { type: Array, default: () => [] },
  enrolled: { type: Array, default: () => [] },
  activeCourse: { type: Object, default: null },
  loading: { type: Boolean, default: false },
});

const emit = defineEmits(["select", "go-home", "back"]);

const searchQuery = ref("");
const debouncedSearch = ref("");
const enrolling = ref(null);
let debounceTimer = null;

const enrolledIds = computed(() => new Set(props.enrolled.map((course) => course.course_id)));
const courseTitleMap = computed(() => new Map(props.courses.map((course) => [course.course_id, course.title_cn])));

const filteredCourses = computed(() => {
  const query = debouncedSearch.value.toLowerCase();
  if (!query) return props.courses;

  return props.courses.filter((course) => (
    course.title_cn?.toLowerCase().includes(query)
    || course.title?.toLowerCase().includes(query)
    || course.description_cn?.toLowerCase().includes(query)
    || (course.tags || []).some((tag) => tag.toLowerCase().includes(query))
  ));
});

onBeforeUnmount(() => {
  clearTimeout(debounceTimer);
});

watch(() => props.loading, (isLoading) => {
  if (!isLoading) enrolling.value = null;
});

function onSearchInput() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    debouncedSearch.value = searchQuery.value.trim();
  }, 180);
}

function resetSearch() {
  searchQuery.value = "";
  debouncedSearch.value = "";
}

function isEnrolled(courseId) {
  return enrolledIds.value.has(courseId);
}

function selectCourse(course) {
  if (props.loading || enrolling.value) return;
  enrolling.value = course.course_id;
  emit("select", course.course_id);
}

function statusLabel(course) {
  if (course.course_id === props.activeCourse?.course_id) return "当前课程";
  if (isEnrolled(course.course_id)) return "已加入";
  return "可选择";
}

function statusClass(course) {
  if (course.course_id === props.activeCourse?.course_id) return "is-current";
  if (isEnrolled(course.course_id)) return "is-enrolled";
  return "";
}

function actionLabel(course) {
  if (course.course_id === props.activeCourse?.course_id) return "继续学习";
  if (isEnrolled(course.course_id)) return "切换课程";
  return "选择课程";
}

function courseCode(course) {
  const codes = {
    data_structures: "DS",
    operating_systems: "OS",
    computer_networks: "NET",
    machine_learning: "ML",
    python_programming: "PY",
  };
  return codes[course.course_id] || String(course.title || course.title_cn || "CO").slice(0, 3).toUpperCase();
}

function difficultyLabel(value) {
  const difficulty = Number(value || 0);
  if (difficulty < 0.45) return "入门";
  if (difficulty < 0.68) return "核心";
  return "进阶";
}

function formatHours(value) {
  const hours = Number(value || 0);
  return hours > 0 ? `${hours} 小时` : "按路径评估";
}

function nodeLabel(value) {
  const count = Number(value || 0);
  return count > 0 ? `${count} 个知识节点` : "学习路径动态生成";
}

function prerequisiteLabel(course) {
  const prerequisites = (course.prerequisites || [])
    .map((courseId) => courseTitleMap.value.get(courseId))
    .filter(Boolean);
  return prerequisites.length ? `建议先学 ${prerequisites.join("、")}` : "";
}
</script>

<style scoped>
.course-page {
  min-height: 100vh;
  min-height: 100dvh;
  background: var(--space-bg);
  color: var(--text-primary);
}

.course-topbar {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--space-panel);
}

.course-topbar__inner {
  display: flex;
  width: min(calc(100% - 2rem), 72rem);
  min-height: 4.5rem;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin: 0 auto;
  padding-top: env(safe-area-inset-top, 0px);
}

.course-brand {
  display: inline-flex;
  align-items: center;
  gap: 0.65rem;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  padding: 0;
  text-align: left;
}

.course-brand__mark {
  display: grid;
  width: 2.5rem;
  aspect-ratio: 1;
  place-items: center;
  border-radius: var(--radius-sm);
  background: var(--text-primary);
  color: var(--space-bg);
  font-size: 0.75rem;
  font-weight: 900;
}

.course-brand__copy {
  display: grid;
  gap: 0.05rem;
}

.course-brand__copy strong {
  font-size: 0.9rem;
}

.course-brand__copy small {
  color: var(--text-muted);
  font-size: 0.68rem;
}

.course-return,
.course-empty-state button,
.course-card__action {
  min-height: 2.65rem;
  border-radius: var(--radius-sm);
  font-size: 0.78rem;
  font-weight: 800;
  transition: transform var(--duration-fast) var(--ease-emphasized), border-color var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard);
}

.course-return {
  border: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-secondary);
  padding: 0.55rem 0.85rem;
}

.course-return:hover {
  border-color: var(--border-strong);
  background: var(--space-elevated);
  color: var(--text-primary);
}

.course-main {
  width: min(calc(100% - 2rem), 72rem);
  margin: 0 auto;
  padding: 3.25rem 0 4rem;
}

.course-heading {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 3rem;
  padding-bottom: 2.25rem;
}

.course-heading h1 {
  margin: 0;
  font-size: 2.25rem;
  font-weight: 900;
  line-height: 1.15;
  text-wrap: balance;
}

.course-heading p {
  max-width: 38rem;
  margin: 0.75rem 0 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.7;
  text-wrap: pretty;
}

.course-search {
  width: min(100%, 20rem);
  flex-shrink: 0;
}

.course-search label {
  display: block;
  margin-bottom: 0.45rem;
  color: var(--text-muted);
  font-size: 0.7rem;
  font-weight: 800;
}

.course-search input {
  width: 100%;
  min-height: 2.8rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--input-bg);
  color: var(--text-primary);
  padding: 0.7rem 0.8rem;
  font: inherit;
  font-size: 0.82rem;
  transition: border-color var(--duration-fast) var(--ease-standard), background var(--duration-fast) var(--ease-standard);
}

.course-search input::placeholder {
  color: var(--text-secondary);
}

.course-search input:hover,
.course-search input:focus {
  border-color: var(--border-strong);
  background: var(--space-surface);
}

.course-list-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid var(--border-strong);
  padding-bottom: 0.8rem;
}

.course-list-heading h2 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 850;
}

.course-list-heading span {
  color: var(--text-muted);
  font-size: 0.72rem;
}

.course-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
  padding-top: 1rem;
}

.course-card,
.course-skeleton {
  min-width: 0;
  min-height: 17.5rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--card-bg);
}

.course-card {
  display: flex;
  flex-direction: column;
  padding: 1.15rem;
  transition: border-color var(--duration-base) var(--ease-standard), background var(--duration-base) var(--ease-standard), transform var(--duration-fast) var(--ease-emphasized);
}

.course-card:hover {
  transform: translateY(-2px);
  border-color: var(--border-strong);
  background: var(--card-bg-hover);
}

.course-card.is-current {
  border-color: color-mix(in srgb, var(--color-primary) 55%, var(--border-subtle));
  background: var(--color-primary-soft);
}

.course-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.course-card__code {
  display: grid;
  width: 3.2rem;
  aspect-ratio: 1;
  place-items: center;
  border-radius: var(--radius-sm);
  background: var(--text-primary);
  color: var(--space-bg);
  font-family: var(--font-mono);
  font-size: 0.78rem;
  font-weight: 850;
}

.course-card__status {
  color: var(--text-muted);
  font-size: 0.66rem;
  font-weight: 800;
}

.course-card__status.is-current,
.course-card__status.is-enrolled {
  color: var(--color-primary-dark);
}

.course-card h2 {
  margin: 1rem 0 0;
  font-size: 1.08rem;
  font-weight: 850;
  text-wrap: balance;
}

.course-card__description {
  display: -webkit-box;
  min-height: 3.75rem;
  margin: 0.5rem 0 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 0.78rem;
  line-height: 1.6;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.course-card__facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  margin: 1rem 0 0;
}

.course-card__facts div {
  min-width: 0;
  border-left: 1px solid var(--border-subtle);
  padding: 0 0.55rem;
}

.course-card__facts div:first-child {
  border-left: 0;
  padding-left: 0;
}

.course-card__facts dt {
  color: var(--text-muted);
  font-size: 0.62rem;
}

.course-card__facts dd {
  margin: 0.25rem 0 0;
  overflow: hidden;
  font-size: 0.7rem;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.course-card__prerequisite {
  min-height: 1rem;
  margin: 0.8rem 0 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 0.66rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.course-card__action {
  width: 100%;
  margin-top: auto;
  border: 1px solid var(--text-primary);
  background: var(--text-primary);
  color: var(--space-bg);
  padding: 0.55rem 0.85rem;
  white-space: nowrap;
}

.course-card__action:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: var(--color-primary-dark);
  background: var(--color-primary-dark);
  color: var(--color-primary-text);
}

.course-return:active,
.course-card__action:active:not(:disabled),
.course-empty-state button:active {
  transform: scale(0.98);
}

.course-card__action:disabled {
  cursor: wait;
  opacity: 0.62;
}

.course-empty-state {
  display: grid;
  min-height: 18rem;
  place-items: center;
  align-content: center;
  border-bottom: 1px solid var(--border-strong);
  text-align: center;
}

.course-empty-state h2 {
  margin: 0;
  font-size: 1rem;
}

.course-empty-state p {
  margin: 0.45rem 0 1.15rem;
  color: var(--text-muted);
  font-size: 0.8rem;
}

.course-empty-state button {
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-primary);
  padding: 0.55rem 0.85rem;
}

.course-skeleton {
  display: flex;
  flex-direction: column;
  padding: 1.15rem;
}

.course-skeleton > div {
  border-radius: var(--radius-xs);
  background: var(--space-elevated);
}

.course-skeleton__code {
  width: 3.2rem;
  aspect-ratio: 1;
}

.course-skeleton__title {
  width: 8rem;
  height: 1rem;
  margin-top: 1rem;
}

.course-skeleton__line {
  width: 100%;
  height: 0.7rem;
  margin-top: 0.75rem;
}

.course-skeleton__line.is-short {
  width: 72%;
  margin-top: 0.45rem;
}

.course-skeleton__meta {
  width: 100%;
  height: 2.2rem;
  margin-top: 1rem;
}

.course-skeleton__action {
  width: 100%;
  height: 2.65rem;
  margin-top: auto;
}

@media (prefers-reduced-motion: no-preference) {
  .course-card {
    animation: course-card-enter 360ms var(--ease-emphasized) backwards;
    animation-delay: calc(var(--course-index, 0) * 45ms);
  }

  .course-skeleton > div {
    animation: course-skeleton-pulse 1.5s var(--ease-standard) infinite alternate;
  }
}

@keyframes course-card-enter {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
}

@keyframes course-skeleton-pulse {
  to {
    opacity: 0.42;
  }
}

@media (max-width: 960px) {
  .course-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .course-topbar__inner,
  .course-main {
    width: min(calc(100% - 2rem), 72rem);
  }

  .course-main {
    padding: 2rem 0 calc(2.5rem + env(safe-area-inset-bottom, 0px));
  }

  .course-heading {
    align-items: stretch;
    flex-direction: column;
    gap: 1.35rem;
    padding-bottom: 1.75rem;
  }

  .course-heading h1 {
    font-size: 1.85rem;
  }

  .course-search {
    width: 100%;
  }

  .course-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .course-card,
  .course-skeleton {
    min-height: 16.5rem;
  }
}

@media (max-width: 430px) {
  .course-brand__copy small {
    display: none;
  }

  .course-return {
    padding-inline: 0.7rem;
  }

  .course-card__facts dd {
    font-size: 0.66rem;
  }
}
</style>
