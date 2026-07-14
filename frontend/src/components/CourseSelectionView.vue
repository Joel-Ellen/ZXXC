<template>
  <section class="relative z-10 min-h-screen px-4 py-8 sm:px-6" aria-labelledby="course-selection-heading">
    <div class="mx-auto w-full max-w-6xl">
      <header class="flex flex-col gap-4 border-b border-subtle pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 id="course-selection-heading" class="text-2xl font-black text-text-primary">选择课程</h1>
          <p class="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">每门课程保留独立的学习路径、节点进度和练习记录。</p>
        </div>
        <button type="button" class="course-touch workspace-shell-btn focus-ring px-5 text-sm font-semibold" @click="emit(returnToWorkspace ? 'back' : 'go-home')">
          {{ returnToWorkspace ? "返回学习" : "返回首页" }}
        </button>
      </header>

      <section class="mt-6 rounded-lg border border-subtle bg-space-panel p-4" aria-label="课程筛选">
        <div class="grid gap-4 sm:grid-cols-[minmax(0,1fr)_14rem]">
          <label>
            <span class="mb-2 block text-xs font-semibold text-text-secondary">搜索课程</span>
            <input
              v-model="searchQuery"
              type="search"
              class="course-touch workspace-shell-input focus-ring w-full rounded-lg px-3 text-sm text-text-primary placeholder:text-text-muted"
              placeholder="名称、介绍或标签"
              autocomplete="off"
            />
          </label>
          <label>
            <span class="mb-2 block text-xs font-semibold text-text-secondary">课程分类</span>
            <select v-model="category" class="course-touch workspace-shell-input focus-ring w-full rounded-lg px-3 text-sm text-text-primary">
              <option value="all">全部分类</option>
              <option v-for="item in categories" :key="item" :value="item">{{ item }}</option>
            </select>
          </label>
        </div>
      </section>

      <div v-if="error" class="mt-6 rounded-lg border border-error/30 bg-error-soft px-5 py-8 text-center" role="alert">
        <h2 class="text-lg font-bold text-text-primary">课程加载失败</h2>
        <p class="mt-2 text-sm text-text-secondary">{{ error }}</p>
        <button type="button" class="course-touch btn-primary focus-ring mt-5 px-5 text-sm font-semibold" @click="emit('retry')">重新加载</button>
      </div>

      <div v-else-if="loading && !courses.length" class="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3" aria-label="正在加载课程">
        <div v-for="index in 6" :key="index" class="animate-pulse rounded-lg border border-subtle bg-space-panel p-5">
          <div class="h-5 w-2/3 rounded bg-space-elevated" />
          <div class="mt-4 h-4 w-full rounded bg-space-elevated" />
          <div class="mt-2 h-4 w-4/5 rounded bg-space-elevated" />
          <div class="mt-6 h-11 w-full rounded bg-space-elevated" />
        </div>
      </div>

      <div v-else-if="!filteredCourses.length" class="mt-6 rounded-lg border border-subtle bg-space-panel px-5 py-12 text-center">
        <h2 class="text-lg font-bold text-text-primary">没有匹配的课程</h2>
        <p class="mt-2 text-sm text-text-secondary">调整关键词或分类后再试。</p>
        <button v-if="hasFilters" type="button" class="course-touch workspace-shell-btn focus-ring mt-5 px-5 text-sm font-semibold" @click="clearFilters">查看全部课程</button>
      </div>

      <div v-else class="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3" :aria-busy="String(loading)">
        <article v-for="course in filteredCourses" :key="course.course_id" class="flex min-w-0 flex-col rounded-lg border border-subtle bg-space-panel p-5">
          <div class="flex items-start gap-3">
            <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-space-elevated text-xl" aria-hidden="true">{{ course.icon || "📘" }}</span>
            <div class="min-w-0 flex-1">
              <div class="flex min-w-0 flex-wrap items-center gap-2">
                <h2 class="truncate text-base font-bold text-text-primary">{{ course.title_cn }}</h2>
                <span v-if="isEnrolled(course.course_id)" class="workspace-shell-chip workspace-shell-chip--success px-2.5 py-1 text-[11px] font-semibold">已加入</span>
              </div>
              <p class="mt-1 text-xs text-text-muted">{{ course.category || "未分类" }}</p>
            </div>
          </div>

          <p class="mt-4 line-clamp-3 text-sm leading-6 text-text-secondary">{{ course.description_cn || "暂无课程介绍。" }}</p>

          <dl class="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-text-muted">
            <div><dt class="inline">节点 </dt><dd class="inline font-semibold text-text-secondary">{{ course.node_count || 0 }}</dd></div>
            <div><dt class="inline">预计 </dt><dd class="inline font-semibold text-text-secondary">{{ course.estimated_hours || 0 }}h</dd></div>
          </dl>

          <div v-if="course.tags?.length" class="mt-4 flex flex-wrap gap-1.5">
            <span v-for="tag in course.tags.slice(0, 4)" :key="tag" class="workspace-shell-chip px-2.5 py-1 text-[11px] text-text-secondary">{{ tag }}</span>
          </div>

          <div v-if="isEnrolled(course.course_id)" class="mt-5">
            <div class="mb-2 flex items-center justify-between text-xs text-text-muted">
              <span>学习进度</span>
              <span>{{ enrollmentProgress(course.course_id) }}%</span>
            </div>
            <div class="h-1.5 overflow-hidden rounded-full bg-space-elevated">
              <div class="h-full rounded-full bg-primary" :style="{ width: `${enrollmentProgress(course.course_id)}%` }" />
            </div>
          </div>

          <div
            v-if="pendingCourse?.course_id === course.course_id"
            class="mt-5 rounded-lg border border-primary/25 bg-primary-soft p-3"
            role="group"
            aria-label="确认课程选择"
          >
            <p class="text-sm font-semibold text-text-primary">{{ confirmationTitle }}</p>
            <p class="mt-1 text-xs leading-5 text-text-secondary">当前课程的学习位置会保留，可随时切回。</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <button type="button" class="course-touch btn-primary focus-ring px-4 text-sm font-semibold" :disabled="loading" @click="confirmSelection">确认</button>
              <button type="button" class="course-touch workspace-shell-btn focus-ring px-4 text-sm font-semibold" :disabled="loading" @click="pendingCourse = null">取消</button>
            </div>
          </div>

          <div class="mt-auto pt-5">
            <button
              type="button"
              class="course-touch btn-primary focus-ring w-full px-4 text-sm font-semibold"
              :disabled="loading"
              @click="requestSelection(course)"
            >
              {{ isEnrolled(course.course_id) ? "选择此课程" : "加入此课程" }}
            </button>
          </div>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  courses: { type: Array, default: () => [] },
  enrolled: { type: Array, default: () => [] },
  activeCourse: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: "" },
  returnToWorkspace: { type: Boolean, default: false },
});

const emit = defineEmits(["select", "back", "go-home", "retry"]);
const searchQuery = ref("");
const category = ref("all");
const pendingCourse = ref(null);

const categories = computed(() => [...new Set(
  props.courses.map((course) => course.category).filter(Boolean),
)].sort((left, right) => left.localeCompare(right, "zh-CN")));

const hasFilters = computed(() => Boolean(searchQuery.value.trim()) || category.value !== "all");

const filteredCourses = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase("zh-CN");
  return props.courses.filter((course) => {
    if (category.value !== "all" && course.category !== category.value) return false;
    if (!query) return true;
    return [course.title_cn, course.title, course.description_cn, course.category, ...(course.tags || [])]
      .join(" ")
      .toLocaleLowerCase("zh-CN")
      .includes(query);
  });
});

const confirmationTitle = computed(() => isEnrolled(pendingCourse.value?.course_id)
  ? `切换到「${pendingCourse.value?.title_cn}」？`
  : `加入并切换到「${pendingCourse.value?.title_cn}」？`
);

function clearFilters() {
  searchQuery.value = "";
  category.value = "all";
}

function enrollmentFor(courseId) {
  return props.enrolled.find((course) => course.course_id === courseId) || null;
}

function isEnrolled(courseId) {
  return Boolean(enrollmentFor(courseId));
}

function enrollmentProgress(courseId) {
  const value = Number(enrollmentFor(courseId)?.progress) || 0;
  const progress = value > 1 && value <= 100 ? value / 100 : value;
  return Math.round(Math.min(1, Math.max(0, progress)) * 100);
}

function requestSelection(course) {
  if (course.course_id === props.activeCourse?.course_id || !props.enrolled.length) {
    emit("select", course.course_id);
    return;
  }
  pendingCourse.value = course;
}

function confirmSelection() {
  if (!pendingCourse.value) return;
  emit("select", pendingCourse.value.course_id);
  pendingCourse.value = null;
}
</script>

<style scoped>
.course-touch {
  min-height: 44px;
}
</style>
