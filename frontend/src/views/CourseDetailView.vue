<template>
  <AppPageFrame>
    <section class="px-4 py-6 sm:px-6 lg:px-8">
      <div class="mx-auto w-full max-w-6xl">
        <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" @click="router.push({ name: 'courses' })">
          返回课程中心
        </button>

        <div v-if="loading" class="mt-6 grid animate-pulse gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]" aria-label="正在加载课程详情">
          <div class="rounded-lg border border-subtle bg-space-panel p-6">
            <div class="h-7 w-1/2 rounded bg-space-elevated" />
            <div class="mt-5 h-4 w-full rounded bg-space-elevated" />
            <div class="mt-2 h-4 w-5/6 rounded bg-space-elevated" />
            <div class="mt-8 h-32 rounded bg-space-elevated" />
          </div>
          <div class="h-64 rounded-lg border border-subtle bg-space-panel" />
        </div>

        <div v-else-if="error" class="mt-6 rounded-lg border border-subtle bg-space-panel px-5 py-12 text-center" role="alert">
          <h1 class="text-xl font-bold text-text-primary">课程详情加载失败</h1>
          <p class="mx-auto mt-2 max-w-xl text-sm leading-6 text-text-secondary">{{ error }}</p>
          <div class="mt-5 flex flex-wrap justify-center gap-2">
            <button type="button" class="course-touch btn-primary focus-ring px-5 text-sm font-semibold" @click="loadCourse">重新加载</button>
            <button type="button" class="course-touch workspace-shell-btn focus-ring px-5 text-sm font-semibold" @click="router.push({ name: 'courses' })">查看其他课程</button>
          </div>
        </div>

        <div v-else-if="courseView" class="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <main class="min-w-0">
            <header class="border-b border-subtle pb-6">
              <div class="flex items-start gap-4">
                <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-space-elevated text-2xl" aria-hidden="true">
                  {{ courseView.icon || "📘" }}
                </span>
                <div class="min-w-0">
                  <p class="text-xs font-semibold text-text-muted">{{ courseView.category || "课程" }}</p>
                  <h1 class="mt-1 text-2xl font-black text-text-primary sm:text-3xl">{{ courseView.title_cn }}</h1>
                </div>
              </div>
              <p class="mt-5 max-w-3xl text-sm leading-7 text-text-secondary">{{ courseView.description_cn || "暂无课程介绍。" }}</p>

              <div v-if="courseView.tags?.length" class="mt-5 flex flex-wrap gap-2">
                <span v-for="tag in courseView.tags" :key="tag" class="workspace-shell-chip px-3 py-1 text-xs text-text-secondary">{{ tag }}</span>
              </div>
            </header>

            <section class="border-b border-subtle py-6" aria-labelledby="course-overview-heading">
              <h2 id="course-overview-heading" class="text-base font-bold text-text-primary">课程概览</h2>
              <dl class="mt-4 grid gap-x-6 gap-y-5 sm:grid-cols-3">
                <div>
                  <dt class="text-xs text-text-muted">知识节点</dt>
                  <dd class="mt-1 text-lg font-bold text-text-primary">{{ courseView.node_count || 0 }}</dd>
                </div>
                <div>
                  <dt class="text-xs text-text-muted">预计学习时长</dt>
                  <dd class="mt-1 text-lg font-bold text-text-primary">{{ courseView.estimated_hours || 0 }} 小时</dd>
                </div>
                <div>
                  <dt class="text-xs text-text-muted">难度</dt>
                  <dd class="mt-1 text-lg font-bold text-text-primary">{{ Math.round((courseView.difficulty || 0) * 100) }} / 100</dd>
                </div>
              </dl>
            </section>

            <section v-if="courseView.prerequisites?.length" class="border-b border-subtle py-6" aria-labelledby="course-prerequisites-heading">
              <h2 id="course-prerequisites-heading" class="text-base font-bold text-text-primary">建议先修</h2>
              <ul class="mt-3 space-y-2 text-sm text-text-secondary">
                <li v-for="prerequisite in courseView.prerequisites" :key="prerequisite" class="flex items-center gap-2">
                  <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-secondary" aria-hidden="true" />
                  <span>{{ prerequisiteTitle(prerequisite) }}</span>
                </li>
              </ul>
            </section>

            <section v-if="enrolledCourse" class="py-6" aria-labelledby="course-progress-heading">
              <div class="flex flex-wrap items-end justify-between gap-2">
                <div>
                  <h2 id="course-progress-heading" class="text-base font-bold text-text-primary">你的学习进度</h2>
                  <p class="mt-1 text-sm text-text-secondary">已完成 {{ enrolledCourse.completed_nodes || 0 }} / {{ enrolledCourse.total_nodes || enrolledCourse.node_count || 0 }} 个节点</p>
                </div>
                <span class="text-lg font-bold text-text-primary">{{ progressPercent }}%</span>
              </div>
              <div
                class="mt-4 h-2 overflow-hidden rounded-full bg-space-elevated"
                role="progressbar"
                aria-label="课程学习进度"
                aria-valuemin="0"
                aria-valuemax="100"
                :aria-valuenow="progressPercent"
              >
                <div class="h-full rounded-full bg-primary transition-[width] duration-200" :style="{ width: `${progressPercent}%` }" />
              </div>

              <div v-if="enrolledCourse.last_node_id" class="mt-5 rounded-lg border border-subtle bg-space-elevated p-4">
                <p class="text-xs text-text-muted">最近位置</p>
                <p class="mt-1 text-sm font-semibold text-text-primary">{{ enrolledCourse.last_node_title || enrolledCourse.last_node_id }}</p>
                <p v-if="enrolledCourse.last_activity_at" class="mt-1 text-xs text-text-muted">{{ formatDate(enrolledCourse.last_activity_at) }}</p>
              </div>

              <div v-if="recentForCourse.length" class="mt-6">
                <h3 class="text-sm font-bold text-text-primary">最近学习</h3>
                <ul class="mt-2 divide-y divide-subtle border-y border-subtle">
                  <li v-for="(item, index) in recentForCourse" :key="`${item.node_id}-${item.occurred_at}-${item.resource_id}-${index}`">
                    <button type="button" class="course-touch flex w-full items-center justify-between gap-4 py-3 text-left focus-ring" @click="openRecent(item)">
                      <span class="min-w-0">
                        <span class="block truncate text-sm font-semibold text-text-primary">{{ item.node_title || item.node_id }}</span>
                        <span class="mt-0.5 block text-xs text-text-muted">{{ eventLabel(item.event_type) }}</span>
                      </span>
                      <span class="shrink-0 text-xs text-text-muted">{{ formatDate(item.occurred_at) }}</span>
                    </button>
                  </li>
                </ul>
              </div>
            </section>
          </main>

          <aside class="rounded-lg border border-subtle bg-space-panel p-5 lg:sticky lg:top-6">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-base font-bold text-text-primary">学习状态</h2>
              <span
                class="workspace-shell-chip px-2.5 py-1 text-[11px] font-semibold"
                :class="isActive ? 'workspace-shell-chip--accent' : ''"
              >
                {{ statusLabel }}
              </span>
            </div>

            <p v-if="lifecycle.errors.enrollment" class="mt-4 rounded-lg border border-warning/30 bg-warning-soft p-3 text-sm leading-6 text-text-primary" role="alert">
              {{ lifecycle.errors.enrollment }}
            </p>
            <p v-if="lifecycle.errors.action" class="mt-4 rounded-lg border border-error/30 bg-error-soft p-3 text-sm leading-6 text-text-primary" role="alert">
              {{ lifecycle.errors.action }}
            </p>

            <div
              v-if="pendingAction"
              class="mt-4 rounded-lg border border-primary/25 bg-primary-soft p-3"
              role="group"
              aria-label="确认课程操作"
            >
              <p class="text-sm font-semibold text-text-primary">{{ confirmationTitle }}</p>
              <p class="mt-1 text-xs leading-5 text-text-secondary">{{ confirmationCopy }}</p>
              <div class="mt-3 flex flex-wrap gap-2">
                <button type="button" class="course-touch btn-primary focus-ring px-4 text-sm font-semibold" :disabled="lifecycle.isActing" @click="confirmAction">确认</button>
                <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" :disabled="lifecycle.isActing" @click="pendingAction = null">取消</button>
              </div>
            </div>

            <div class="mt-5 grid gap-2">
              <button
                type="button"
                class="course-touch btn-primary focus-ring w-full px-4 text-sm font-semibold"
                :disabled="lifecycle.isActing || Boolean(lifecycle.errors.enrollment)"
                @click="requestPrimaryAction"
              >
                {{ primaryActionLabel }}
              </button>
              <button
                v-if="enrolledCourse"
                type="button"
                class="course-touch workspace-shell-btn workspace-shell-btn--danger focus-ring w-full px-4 text-sm font-semibold"
                :disabled="lifecycle.isActing"
                @click="pendingAction = { type: 'leave' }"
              >
                退出课程
              </button>
              <button
                v-if="lifecycle.errors.enrollment"
                type="button"
                class="course-touch workspace-shell-btn focus-ring w-full px-4 text-sm font-semibold"
                @click="retryEnrollment"
              >
                重试同步
              </button>
              <button
                v-if="lifecycle.errors.summary"
                type="button"
                class="course-touch workspace-shell-btn focus-ring w-full px-4 text-sm font-semibold"
                @click="lifecycle.loadSummary({ force: true })"
              >
                重试学习摘要
              </button>
            </div>
            <p v-if="lifecycle.errors.summary" class="mt-3 text-xs leading-5 text-text-muted" role="alert">最近位置暂未同步：{{ lifecycle.errors.summary }}</p>
          </aside>
        </div>
      </div>
    </section>
  </AppPageFrame>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import AppPageFrame from "../components/AppPageFrame.vue";
import { courseLifecycleErrorMessage, fetchCourseById } from "../services/courseLifecycleApi";
import { useCourseLifecycleStore } from "../stores/courseLifecycle";

const props = defineProps({ courseId: { type: String, required: true } });
const router = useRouter();
const lifecycle = useCourseLifecycleStore();
const course = ref(null);
const loading = ref(true);
const error = ref("");
const pendingAction = ref(null);
let loadVersion = 0;

const enrolledCourse = computed(() => lifecycle.enrolledCourses.find((item) => item.course_id === props.courseId) || null);
const courseView = computed(() => ({ ...(course.value || {}), ...(enrolledCourse.value || {}) }));
const isActive = computed(() => lifecycle.activeCourse?.course_id === props.courseId);
const progressPercent = computed(() => Math.round(Math.min(1, Math.max(0, Number(enrolledCourse.value?.progress) || 0)) * 100));
const recentForCourse = computed(() => lifecycle.recentLearning.filter((item) => item.course_id === props.courseId).slice(0, 4));
const statusLabel = computed(() => isActive.value ? "当前课程" : enrolledCourse.value ? "已加入" : "未加入");

const primaryActionLabel = computed(() => {
  if (lifecycle.action.courseId === props.courseId) {
    if (lifecycle.action.type === "switch") return "正在切换…";
    if (lifecycle.action.type === "enroll") return "正在加入…";
  }
  if (isActive.value) return "继续学习";
  if (enrolledCourse.value) return "切换并学习";
  return "加入课程";
});

const confirmationTitle = computed(() => {
  if (pendingAction.value?.type === "leave") return `退出「${courseView.value.title_cn}」？`;
  if (pendingAction.value?.type === "switch") return `切换到「${courseView.value.title_cn}」？`;
  return `加入并切换到「${courseView.value.title_cn}」？`;
});

const confirmationCopy = computed(() => pendingAction.value?.type === "leave"
  ? "课程学习记录会按服务端规则处理。此操作完成后将返回课程中心。"
  : "当前课程的学习位置会保留，可随时切回。"
);

watch(() => props.courseId, loadCourse, { immediate: true });

async function loadCourse() {
  const version = ++loadVersion;
  loading.value = true;
  error.value = "";
  pendingAction.value = null;
  lifecycle.clearActionError();
  const [courseResult] = await Promise.allSettled([
    fetchCourseById(props.courseId),
    lifecycle.loadDashboard({ force: true }),
  ]);
  if (version !== loadVersion) return;
  if (courseResult.status === "fulfilled") {
    course.value = courseResult.value;
  } else {
    course.value = null;
    error.value = courseLifecycleErrorMessage(courseResult.reason, "无法加载此课程。");
  }
  loading.value = false;
}

function retryEnrollment() {
  Promise.all([
    lifecycle.loadEnrollment({ force: true }),
    lifecycle.loadSummary({ force: true }),
  ]);
}

function prerequisiteTitle(courseId) {
  return lifecycle.catalog.find((item) => item.course_id === courseId)?.title_cn || courseId;
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

function eventLabel(type) {
  return {
    lesson_opened: "打开课程节点",
    content_viewed: "查看学习内容",
    hint_requested: "请求学习提示",
    answer_selected: "选择练习答案",
    lesson_completed: "完成课程节点",
    answer_submitted: "提交练习答案",
    code_run: "运行代码练习",
    code_submitted: "提交代码练习",
    review_completed: "完成复习任务",
    tutor_question: "向导师提问",
  }[type] || "学习记录";
}

function targetNode(nodeId = "") {
  const declared = lifecycle.continueLearning;
  if (nodeId) return nodeId;
  if (declared?.course_id === props.courseId) return declared.node_id;
  return enrolledCourse.value?.last_node_id || "setup";
}

function goToLearning(nodeId = "") {
  router.push({
    name: "learn",
    params: { courseId: props.courseId, nodeId: targetNode(nodeId) },
  });
}

function requestPrimaryAction() {
  lifecycle.clearActionError();
  if (isActive.value) {
    goToLearning();
    return;
  }
  if (enrolledCourse.value) {
    pendingAction.value = { type: "switch" };
    return;
  }
  if (lifecycle.activeCourse) {
    pendingAction.value = { type: "enroll" };
    return;
  }
  void enrollAndContinue();
}

function openRecent(item) {
  if (isActive.value) {
    goToLearning(item.node_id);
    return;
  }
  pendingAction.value = { type: "switch", nodeId: item.node_id };
}

async function confirmAction() {
  const pending = pendingAction.value;
  if (!pending) return;
  if (pending.type === "leave") {
    const succeeded = await lifecycle.leaveCourse(props.courseId);
    if (succeeded) await router.push({ name: "courses" });
    return;
  }
  const succeeded = pending.type === "switch"
    ? await lifecycle.activateCourse(props.courseId)
    : await lifecycle.enrollCourse(props.courseId);
  if (!succeeded) return;
  pendingAction.value = null;
  goToLearning(pending.nodeId || "");
}

async function enrollAndContinue() {
  const succeeded = await lifecycle.enrollCourse(props.courseId);
  if (succeeded) goToLearning();
}
</script>

<style scoped>
.course-touch {
  min-height: 44px;
}

@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: 0.01ms !important;
  }
}
</style>
