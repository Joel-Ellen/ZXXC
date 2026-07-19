<template>
  <AppPageFrame>
    <section class="px-4 py-6 sm:px-6 lg:px-8">
      <div class="mx-auto w-full max-w-7xl">
        <header class="flex flex-col gap-4 border-b border-subtle pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 class="text-2xl font-black text-text-primary">课程中心</h1>
            <p class="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">查找课程，查看学习范围，并管理你的学习列表。</p>
          </div>
          <p v-if="!lifecycle.loading.catalog && !lifecycle.errors.catalog" class="text-sm text-text-muted" aria-live="polite">
            {{ filteredCourses.length }} 门匹配课程
          </p>
        </header>

        <div
          v-if="lifecycle.errors.action"
          class="mt-5 flex flex-col gap-3 rounded-lg border border-error/30 bg-error-soft px-4 py-3 text-sm text-text-primary sm:flex-row sm:items-center sm:justify-between"
          role="alert"
        >
          <span>{{ lifecycle.errors.action }}</span>
          <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" @click="lifecycle.clearActionError">
            关闭
          </button>
        </div>

        <div
          v-if="lifecycle.errors.enrollment"
          class="mt-5 flex flex-col gap-3 rounded-lg border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-text-primary sm:flex-row sm:items-center sm:justify-between"
          role="alert"
        >
          <span>课程状态未同步：{{ lifecycle.errors.enrollment }}</span>
          <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" @click="retryEnrollment">
            重试
          </button>
        </div>

        <div
          v-if="lifecycle.errors.catalog && lifecycle.catalog.length"
          class="mt-5 flex flex-col gap-3 rounded-lg border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-text-primary sm:flex-row sm:items-center sm:justify-between"
          role="alert"
        >
          <span>课程目录可能不是最新状态：{{ lifecycle.errors.catalog }}</span>
          <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" @click="reloadCatalog">重试</button>
        </div>

        <section class="mt-6 rounded-lg border border-subtle bg-space-panel p-4 sm:p-5" aria-label="课程筛选">
          <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_15rem_auto] lg:items-end">
            <label class="min-w-0">
              <span class="mb-2 block text-xs font-semibold text-text-secondary">搜索课程</span>
              <input
                v-model="filters.search"
                type="search"
                class="course-touch workspace-shell-input focus-ring w-full rounded-lg px-3 text-sm text-text-primary placeholder:text-text-muted"
                placeholder="名称、介绍或标签"
                autocomplete="off"
              />
            </label>

            <label>
              <span class="mb-2 block text-xs font-semibold text-text-secondary">课程分类</span>
              <select
                v-model="filters.category"
                class="course-touch workspace-shell-input focus-ring w-full rounded-lg px-3 text-sm text-text-primary"
              >
                <option value="all">全部分类</option>
                <option v-for="category in categories" :key="category" :value="category">{{ category }}</option>
              </select>
            </label>

            <button
              type="button"
              class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold"
              :disabled="!hasFilters"
              @click="clearFilters"
            >
              清除筛选
            </button>
          </div>
        </section>

        <section class="mt-6" aria-live="polite" :aria-busy="String(lifecycle.loading.catalog)">
          <div v-if="lifecycle.loading.catalog && !lifecycle.catalog.length" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div v-for="index in 6" :key="index" class="course-card animate-pulse rounded-lg border border-subtle bg-space-panel p-5">
              <div class="h-5 w-2/3 rounded bg-space-elevated" />
              <div class="mt-4 h-4 w-full rounded bg-space-elevated" />
              <div class="mt-2 h-4 w-4/5 rounded bg-space-elevated" />
              <div class="mt-6 h-11 w-full rounded bg-space-elevated" />
            </div>
          </div>

          <div v-else-if="lifecycle.errors.catalog && !lifecycle.catalog.length" class="rounded-lg border border-subtle bg-space-panel px-5 py-12 text-center">
            <h2 class="text-lg font-bold text-text-primary">课程目录加载失败</h2>
            <p class="mx-auto mt-2 max-w-xl text-sm leading-6 text-text-secondary">{{ lifecycle.errors.catalog }}</p>
            <button type="button" class="course-touch btn-primary focus-ring mt-5 px-5 text-sm font-semibold" @click="reloadCatalog">
              重新加载
            </button>
          </div>

          <div v-else-if="!filteredCourses.length" class="rounded-lg border border-subtle bg-space-panel px-5 py-12 text-center">
            <h2 class="text-lg font-bold text-text-primary">没有匹配的课程</h2>
            <p class="mt-2 text-sm text-text-secondary">调整关键词或分类后再试。</p>
            <button v-if="hasFilters" type="button" class="course-touch workspace-shell-btn focus-ring mt-5 px-5 text-sm font-semibold" @click="clearFilters">
              查看全部课程
            </button>
          </div>

          <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <article
              v-for="course in filteredCourses"
              :key="course.course_id"
              class="course-card flex min-w-0 flex-col rounded-lg border border-subtle bg-space-panel p-5"
            >
              <div class="flex items-start gap-3">
                <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-space-elevated text-text-secondary" aria-hidden="true">
                  <CourseIcon :course-id="course.course_id" :icon="course.icon" :size="24" />
                </span>
                <div class="min-w-0 flex-1">
                  <div class="flex min-w-0 flex-wrap items-center gap-2">
                    <h2 class="min-w-0 truncate text-base font-bold text-text-primary">{{ course.title_cn }}</h2>
                    <span v-if="isActive(course)" class="workspace-shell-chip workspace-shell-chip--accent px-2.5 py-1 text-[11px] font-semibold">当前课程</span>
                    <span v-else-if="course.enrolled" class="workspace-shell-chip px-2.5 py-1 text-[11px] font-semibold text-text-secondary">已加入</span>
                  </div>
                  <p class="mt-1 text-xs text-text-muted">{{ course.category || "未分类" }}</p>
                </div>
              </div>

              <p class="mt-4 line-clamp-3 text-sm leading-6 text-text-secondary">
                {{ course.description_cn || "暂无课程介绍。" }}
              </p>

              <dl class="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-text-muted">
                <div><dt class="inline">节点 </dt><dd class="inline font-semibold text-text-secondary">{{ course.node_count }}</dd></div>
                <div><dt class="inline">学时 </dt><dd class="inline font-semibold text-text-secondary">{{ course.estimated_hours }}h</dd></div>
                <div><dt class="inline">难度 </dt><dd class="inline font-semibold text-text-secondary">{{ difficultyLabel(course.difficulty) }}</dd></div>
              </dl>

              <div v-if="course.tags?.length" class="mt-4 flex flex-wrap gap-1.5">
                <span v-for="tag in course.tags.slice(0, 4)" :key="tag" class="workspace-shell-chip px-2.5 py-1 text-[11px] text-text-secondary">{{ tag }}</span>
              </div>

              <div v-if="course.enrolled" class="mt-5">
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
                <p class="mt-2 text-xs text-text-muted">已完成 {{ course.completed_nodes || 0 }} / {{ course.total_nodes || course.node_count || 0 }} 个节点</p>
              </div>

              <div
                v-if="pendingAction?.courseId === course.course_id"
                class="mt-5 rounded-lg border border-primary/25 bg-primary-soft p-3"
                role="group"
                :aria-label="pendingAction.type === 'switch' ? '确认切换课程' : '确认加入课程'"
              >
                <p class="text-sm font-semibold text-text-primary">
                  {{ pendingAction.type === "switch" ? `切换到「${course.title_cn}」？` : `加入并切换到「${course.title_cn}」？` }}
                </p>
                <p class="mt-1 text-xs leading-5 text-text-secondary">当前学习位置会保留，可随时切回。</p>
                <div class="mt-3 flex flex-wrap gap-2">
                  <button type="button" class="course-touch btn-primary focus-ring px-4 text-sm font-semibold" :disabled="lifecycle.isActing" @click="confirmAction(course)">
                    确认
                  </button>
                  <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" :disabled="lifecycle.isActing" @click="pendingAction = null">
                    取消
                  </button>
                </div>
              </div>

              <div class="mt-auto flex flex-wrap gap-2 pt-5">
                <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" @click="openDetail(course)">
                  查看详情
                </button>
                <button
                  type="button"
                  class="course-touch btn-primary focus-ring px-4 text-sm font-semibold"
                  :disabled="lifecycle.isActing || Boolean(lifecycle.errors.enrollment)"
                  @click="requestPrimaryAction(course)"
                >
                  {{ primaryActionLabel(course) }}
                </button>
              </div>
            </article>
          </div>
        </section>
      </div>
    </section>
  </AppPageFrame>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import AppPageFrame from "../components/AppPageFrame.vue";
import CourseIcon from "../components/icons/CourseIcon.vue";
import { useCourseLifecycleStore } from "../stores/courseLifecycle";

const router = useRouter();
const lifecycle = useCourseLifecycleStore();
const filters = reactive({ search: "", category: "all" });
const pendingAction = ref(null);

const categories = computed(() => [...new Set(
  lifecycle.catalog.map((course) => course.category).filter(Boolean),
)].sort((left, right) => left.localeCompare(right, "zh-CN")));

const hasFilters = computed(() => Boolean(filters.search.trim()) || filters.category !== "all");

const filteredCourses = computed(() => {
  const query = filters.search.trim().toLocaleLowerCase("zh-CN");
  return lifecycle.catalogCourses.filter((course) => {
    if (filters.category !== "all" && course.category !== filters.category) return false;
    if (!query) return true;
    const searchable = [
      course.title_cn,
      course.title,
      course.description_cn,
      course.description,
      course.category,
      ...(course.tags || []),
    ].join(" ").toLocaleLowerCase("zh-CN");
    return searchable.includes(query);
  });
});

onMounted(() => lifecycle.loadDashboard({ force: true }));

function clearFilters() {
  filters.search = "";
  filters.category = "all";
}

function reloadCatalog() {
  lifecycle.loadCatalog({ force: true });
}

function retryEnrollment() {
  Promise.all([
    lifecycle.loadEnrollment({ force: true }),
    lifecycle.loadSummary({ force: true }),
  ]);
}

function isActive(course) {
  return lifecycle.activeCourse?.course_id === course.course_id;
}

function progressPercent(course) {
  return Math.round(Math.min(1, Math.max(0, Number(course.progress) || 0)) * 100);
}

function difficultyLabel(value) {
  const score = Math.round((Number(value) || 0) * 100);
  if (score < 35) return `入门 · ${score}`;
  if (score < 70) return `进阶 · ${score}`;
  return `挑战 · ${score}`;
}

function primaryActionLabel(course) {
  if (lifecycle.action.courseId === course.course_id) {
    if (lifecycle.action.type === "switch") return "正在切换…";
    if (lifecycle.action.type === "enroll") return "正在加入…";
  }
  if (isActive(course)) return "继续学习";
  if (course.enrolled) return "切换并学习";
  return "加入课程";
}

function openDetail(course) {
  router.push({ name: "course-detail", params: { courseId: course.course_id } });
}

function learningNode(course) {
  const declared = lifecycle.continueLearning;
  if (declared?.course_id === course.course_id) return declared.node_id;
  return course.last_node_id || "setup";
}

function goToLearning(course) {
  router.push({
    name: "learn",
    params: { courseId: course.course_id, nodeId: learningNode(course) },
  });
}

function requestPrimaryAction(course) {
  lifecycle.clearActionError();
  if (isActive(course)) {
    goToLearning(course);
    return;
  }

  if (course.enrolled) {
    pendingAction.value = { type: "switch", courseId: course.course_id };
    return;
  }

  if (lifecycle.activeCourse) {
    pendingAction.value = { type: "enroll", courseId: course.course_id };
    return;
  }

  void enrollAndLearn(course);
}

async function confirmAction(course) {
  const type = pendingAction.value?.type;
  if (!type || pendingAction.value?.courseId !== course.course_id) return;
  const succeeded = type === "switch"
    ? await lifecycle.activateCourse(course.course_id)
    : await lifecycle.enrollCourse(course.course_id);
  if (!succeeded) return;
  pendingAction.value = null;
  const enrolled = lifecycle.enrolledCourses.find((item) => item.course_id === course.course_id) || course;
  goToLearning(enrolled);
}

async function enrollAndLearn(course) {
  const succeeded = await lifecycle.enrollCourse(course.course_id);
  if (!succeeded) return;
  const enrolled = lifecycle.enrolledCourses.find((item) => item.course_id === course.course_id) || course;
  goToLearning(enrolled);
}
</script>

<style scoped>
.course-touch {
  min-height: 44px;
}

.course-card {
  transition: border-color 180ms ease, background-color 180ms ease;
}

.course-card:hover {
  border-color: color-mix(in srgb, var(--color-primary) 22%, var(--border-subtle));
  background: var(--card-bg-hover);
}

@media (prefers-reduced-motion: reduce) {
  .course-card,
  .course-card * {
    transition-duration: 0.01ms !important;
  }
}
</style>
