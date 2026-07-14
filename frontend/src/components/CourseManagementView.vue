<template>
  <section aria-labelledby="managed-courses-heading">
    <header class="flex flex-col gap-4 border-b border-subtle pb-6 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h1 id="managed-courses-heading" class="text-2xl font-black text-text-primary">
          {{ activeCourse ? `继续 ${activeCourse.title_cn}` : "我的课程" }}
        </h1>
        <p class="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
          {{ activeCourse ? activeSummary : "选择一门课程后，学习位置和进度会显示在这里。" }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          v-if="activeCourse"
          type="button"
          class="course-touch btn-primary focus-ring px-5 text-sm font-semibold"
          :disabled="busy"
          @click="$emit('continue-course', activeCourse.course_id)"
        >
          继续学习
        </button>
        <button type="button" class="course-touch workspace-shell-btn focus-ring px-5 text-sm font-semibold" @click="$emit('open-catalog')">
          浏览课程
        </button>
      </div>
    </header>

    <div
      v-if="actionError"
      class="mt-5 flex flex-col gap-3 rounded-lg border border-error/30 bg-error-soft px-4 py-3 text-sm text-text-primary sm:flex-row sm:items-center sm:justify-between"
      role="alert"
    >
      <span>{{ actionError }}</span>
      <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" @click="$emit('dismiss-error')">关闭</button>
    </div>

    <div
      v-if="error && courses.length"
      class="mt-5 flex flex-col gap-3 rounded-lg border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-text-primary sm:flex-row sm:items-center sm:justify-between"
      role="alert"
    >
      <span>已选课程可能不是最新状态：{{ error }}</span>
      <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" @click="$emit('retry')">重试</button>
    </div>

    <div class="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <section aria-label="已选课程" :aria-busy="String(loading)">
        <div v-if="loading && !courses.length" class="grid gap-4 md:grid-cols-2">
          <div v-for="index in 4" :key="index" class="animate-pulse rounded-lg border border-subtle bg-space-panel p-5">
            <div class="h-5 w-1/2 rounded bg-space-elevated" />
            <div class="mt-4 h-4 w-full rounded bg-space-elevated" />
            <div class="mt-2 h-4 w-4/5 rounded bg-space-elevated" />
            <div class="mt-6 h-11 w-full rounded bg-space-elevated" />
          </div>
        </div>

        <div v-else-if="error && !courses.length" class="rounded-lg border border-subtle bg-space-panel px-5 py-12 text-center" role="alert">
          <h2 class="text-lg font-bold text-text-primary">已选课程加载失败</h2>
          <p class="mx-auto mt-2 max-w-xl text-sm leading-6 text-text-secondary">{{ error }}</p>
          <button type="button" class="course-touch btn-primary focus-ring mt-5 px-5 text-sm font-semibold" @click="$emit('retry')">重新加载</button>
        </div>

        <div v-else-if="!courses.length" class="rounded-lg border border-subtle bg-space-panel px-5 py-12 text-center">
          <h2 class="text-lg font-bold text-text-primary">还没有已选课程</h2>
          <p class="mt-2 text-sm text-text-secondary">从课程中心加入一门课程开始学习。</p>
          <button type="button" class="course-touch btn-primary focus-ring mt-5 px-5 text-sm font-semibold" @click="$emit('open-catalog')">前往课程中心</button>
        </div>

        <div v-else class="grid gap-4 md:grid-cols-2">
          <article
            v-for="course in courses"
            :key="course.course_id"
            class="managed-course flex min-w-0 flex-col rounded-lg border border-subtle bg-space-panel p-5"
          >
            <div class="flex items-start gap-3">
              <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-space-elevated text-xl" aria-hidden="true">{{ course.icon || "📘" }}</span>
              <div class="min-w-0 flex-1">
                <div class="flex min-w-0 flex-wrap items-center gap-2">
                  <h2 class="truncate text-base font-bold text-text-primary">{{ course.title_cn }}</h2>
                  <span
                    class="workspace-shell-chip px-2.5 py-1 text-[11px] font-semibold"
                    :class="course.course_id === activeCourse?.course_id ? 'workspace-shell-chip--accent' : ''"
                  >
                    {{ course.course_id === activeCourse?.course_id ? "当前课程" : "已加入" }}
                  </span>
                </div>
                <p class="mt-1 text-xs text-text-muted">{{ course.category || "未分类" }}</p>
              </div>
            </div>

            <p class="mt-4 line-clamp-2 text-sm leading-6 text-text-secondary">{{ course.description_cn || "暂无课程介绍。" }}</p>

            <div class="mt-5">
              <div class="mb-2 flex items-center justify-between text-xs text-text-muted">
                <span>学习进度</span>
                <span>{{ progressPercent(course) }}%</span>
              </div>
              <div
                class="h-1.5 overflow-hidden rounded-full bg-space-elevated"
                role="progressbar"
                aria-label="课程学习进度"
                aria-valuemin="0"
                aria-valuemax="100"
                :aria-valuenow="progressPercent(course)"
              >
                <div class="h-full rounded-full bg-primary transition-[width] duration-200" :style="{ width: `${progressPercent(course)}%` }" />
              </div>
              <div class="mt-2 flex flex-wrap justify-between gap-2 text-xs text-text-muted">
                <span>已完成 {{ course.completed_nodes || 0 }} / {{ course.total_nodes || course.node_count || 0 }} 个节点</span>
                <span v-if="course.last_activity_at">{{ formatDate(course.last_activity_at) }}</span>
              </div>
            </div>

            <p v-if="course.last_node_id" class="mt-4 text-sm text-text-secondary">
              最近位置：<span class="font-semibold text-text-primary">{{ course.last_node_title || course.last_node_id }}</span>
            </p>

            <div
              v-if="pendingAction?.source === 'course' && pendingAction.course.course_id === course.course_id"
              class="mt-4 rounded-lg border border-primary/25 bg-primary-soft p-3"
              role="group"
              aria-label="确认课程操作"
            >
              <p class="text-sm font-semibold text-text-primary">{{ pendingTitle }}</p>
              <p class="mt-1 text-xs leading-5 text-text-secondary">{{ pendingCopy }}</p>
              <div class="mt-3 flex flex-wrap gap-2">
                <button type="button" class="course-touch btn-primary focus-ring px-4 text-sm font-semibold" :disabled="busy" @click="confirmPending">确认</button>
                <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" :disabled="busy" @click="pendingAction = null">取消</button>
              </div>
            </div>

            <div class="mt-auto flex flex-wrap gap-2 pt-5">
              <button
                type="button"
                class="course-touch btn-primary focus-ring px-4 text-sm font-semibold"
                :disabled="busy"
                @click="requestEnter(course)"
              >
                {{ actionLabel(course) }}
              </button>
              <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" @click="$emit('view-course', course.course_id)">
                查看详情
              </button>
              <button
                type="button"
                class="course-touch workspace-shell-btn workspace-shell-btn--danger focus-ring px-4 text-sm font-semibold"
                :disabled="busy"
                @click="pendingAction = { type: 'leave', course, source: 'course' }"
              >
                退出课程
              </button>
            </div>
          </article>
        </div>
      </section>

      <aside class="rounded-lg border border-subtle bg-space-panel p-5" aria-labelledby="recent-learning-heading">
        <div class="flex items-center justify-between gap-3">
          <h2 id="recent-learning-heading" class="text-base font-bold text-text-primary">最近学习</h2>
          <span v-if="availableRecentLearning.length" class="text-xs text-text-muted">{{ availableRecentLearning.length }} 条</span>
        </div>

        <div
          v-if="pendingAction?.source === 'recent'"
          class="mt-4 rounded-lg border border-primary/25 bg-primary-soft p-3"
          role="group"
          aria-label="确认切换课程"
        >
          <p class="text-sm font-semibold text-text-primary">{{ pendingTitle }}</p>
          <p class="mt-1 text-xs leading-5 text-text-secondary">{{ pendingCopy }}</p>
          <div class="mt-3 flex flex-wrap gap-2">
            <button type="button" class="course-touch btn-primary focus-ring px-4 text-sm font-semibold" :disabled="busy" @click="confirmPending">确认</button>
            <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" :disabled="busy" @click="pendingAction = null">取消</button>
          </div>
        </div>

        <div v-if="summaryError" class="mt-4 rounded-lg border border-warning/30 bg-warning-soft p-3" role="alert">
          <p class="text-sm leading-6 text-text-primary">{{ summaryError }}</p>
          <button type="button" class="course-touch workspace-shell-btn focus-ring mt-3 px-4 text-sm font-semibold" @click="$emit('retry-summary')">重试</button>
        </div>

        <div v-if="summaryLoading && !availableRecentLearning.length" class="mt-4 space-y-3" aria-label="正在加载最近学习">
          <div v-for="index in 3" :key="index" class="animate-pulse border-b border-subtle pb-3">
            <div class="h-4 w-3/4 rounded bg-space-elevated" />
            <div class="mt-2 h-3 w-1/2 rounded bg-space-elevated" />
          </div>
        </div>

        <p v-else-if="!availableRecentLearning.length && !summaryError" class="mt-4 text-sm leading-6 text-text-secondary">完成一次真实学习行为后，这里会显示最近位置。</p>

        <ul v-else-if="availableRecentLearning.length" class="mt-3 divide-y divide-subtle">
          <li v-for="(item, index) in availableRecentLearning.slice(0, 8)" :key="`${item.course_id}-${item.node_id}-${item.occurred_at}-${item.resource_id}-${index}`">
            <button type="button" class="course-touch w-full py-3 text-left focus-ring" @click="requestRecent(item)">
              <span class="block truncate text-sm font-semibold text-text-primary">{{ item.node_title || item.node_id }}</span>
              <span class="mt-1 block truncate text-xs text-text-muted">{{ item.course_title }} · {{ formatDate(item.occurred_at) }}</span>
            </button>
          </li>
        </ul>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  courses: { type: Array, default: () => [] },
  activeCourse: { type: Object, default: null },
  recentLearning: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  summaryLoading: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  error: { type: String, default: "" },
  summaryError: { type: String, default: "" },
  actionError: { type: String, default: "" },
  actionCourseId: { type: String, default: "" },
  actionType: { type: String, default: "" },
});

const emit = defineEmits([
  "open-catalog",
  "continue-course",
  "activate-course",
  "view-course",
  "leave-course",
  "open-recent",
  "retry",
  "retry-summary",
  "dismiss-error",
]);

const pendingAction = ref(null);
const enrolledCourseIds = computed(() => new Set(props.courses.map((course) => course.course_id)));
const availableRecentLearning = computed(() => props.recentLearning.filter((item) => (
  enrolledCourseIds.value.has(item.course_id)
)));

const activeSummary = computed(() => {
  const percent = progressPercent(props.activeCourse);
  const lastNode = props.activeCourse?.last_node_title || props.activeCourse?.last_node_id;
  return lastNode ? `${percent}% 已完成，上次学到「${lastNode}」。` : `${percent}% 已完成。`;
});

const pendingTitle = computed(() => {
  const courseTitle = pendingAction.value?.course?.title_cn || "该课程";
  return pendingAction.value?.type === "leave" ? `退出「${courseTitle}」？` : `切换到「${courseTitle}」？`;
});

const pendingCopy = computed(() => pendingAction.value?.type === "leave"
  ? "退出后，这门课程将从你的课程列表移除。"
  : "当前课程的学习位置会保留，可随时切回。"
);

function progressPercent(course) {
  return Math.round(Math.min(1, Math.max(0, Number(course?.progress) || 0)) * 100);
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function actionLabel(course) {
  if (props.actionCourseId === course.course_id) {
    if (props.actionType === "switch") return "正在切换…";
    if (props.actionType === "leave") return "正在退出…";
  }
  return course.course_id === props.activeCourse?.course_id ? "继续学习" : "切换并学习";
}

function requestEnter(course) {
  if (course.course_id === props.activeCourse?.course_id) {
    emit("continue-course", course.course_id);
    return;
  }
  pendingAction.value = { type: "switch", course, source: "course" };
}

function requestRecent(item) {
  if (item.course_id === props.activeCourse?.course_id) {
    emit("open-recent", item);
    return;
  }
  const course = props.courses.find((candidate) => candidate.course_id === item.course_id);
  if (!course) return;
  pendingAction.value = { type: "switch", course, nodeId: item.node_id, source: "recent" };
}

function confirmPending() {
  const pending = pendingAction.value;
  if (!pending) return;
  if (pending.type === "leave") {
    emit("leave-course", pending.course.course_id);
  } else {
    emit("activate-course", pending.course.course_id, pending.nodeId || "");
  }
  pendingAction.value = null;
}
</script>

<style scoped>
.course-touch {
  min-height: 44px;
}

.managed-course {
  transition: border-color 180ms ease, background-color 180ms ease;
}

.managed-course:hover {
  border-color: color-mix(in srgb, var(--color-primary) 22%, var(--border-subtle));
  background: var(--card-bg-hover);
}

@media (prefers-reduced-motion: reduce) {
  .managed-course,
  .managed-course * {
    transition-duration: 0.01ms !important;
  }
}
</style>
