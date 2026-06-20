<template>
  <div class="relative z-10 flex min-h-screen flex-col items-center justify-center px-4 py-16 animate-fadeIn">
    <div class="w-full max-w-4xl">
      <!-- Header -->
      <div class="mb-12 text-center">
        <p class="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-primary">课程选择</p>
        <h1 class="text-4xl font-black tracking-tight sm:text-5xl">
          选择你的<br class="hidden sm:block" />
          <span class="gradient-text">学习起点。</span>
        </h1>
        <p class="mx-auto mt-4 max-w-xl text-base font-light leading-relaxed text-text-secondary">
          每门课程拥有独立的学习画像、知识路径与能力雷达。选择后可通过冷启动测评获得个性化学习规划。
        </p>
      </div>

      <!-- Search bar -->
      <div class="reveal mb-8">
        <div class="relative mx-auto max-w-lg">
          <svg
            width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" class="absolute left-4 top-1/2 -translate-y-1/2 text-text-muted"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索课程名称、标签..."
            class="w-full rounded-2xl border border-subtle bg-card py-3.5 pl-11 pr-4 text-sm font-light text-text-primary placeholder:text-text-muted outline-none transition-all duration-200 focus:border-primary/40 focus:bg-card-hover focus:shadow-card"
            @input="onSearchInput"
          />
        </div>
      </div>

      <!-- Loading state -->
      <div v-if="loading" class="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <div v-for="i in 3" :key="i" class="animate-pulse rounded-[28px] border border-subtle bg-card p-6">
          <div class="mb-4 flex items-center justify-between">
            <div class="h-11 w-11 rounded-2xl bg-space-surface" />
            <div class="h-4 w-16 rounded-full bg-space-surface" />
          </div>
          <div class="h-5 w-2/3 rounded bg-space-surface" />
          <div class="mt-3 h-4 w-full rounded bg-space-surface" />
          <div class="mt-2 h-4 w-4/5 rounded bg-space-surface" />
          <div class="mt-4 flex gap-1.5">
            <div class="h-6 w-12 rounded-full bg-space-surface" />
            <div class="h-6 w-16 rounded-full bg-space-surface" />
            <div class="h-6 w-10 rounded-full bg-space-surface" />
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-else-if="!filteredCourses.length" class="py-20 text-center">
        <div class="mx-auto mb-5 flex h-20 w-20 items-center justify-center rounded-full bg-card border border-subtle">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-text-muted">
            <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
          </svg>
        </div>
        <p class="text-base font-medium text-text-secondary">未找到匹配课程</p>
        <p class="mt-1 text-sm text-text-muted">试试其他关键词</p>
      </div>

      <!-- Course grid -->
      <div v-else class="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <button
          v-for="(course, idx) in filteredCourses"
          :key="course.course_id"
          type="button"
          class="reveal group relative flex flex-col overflow-hidden rounded-[28px] border border-subtle bg-card p-6 text-left transition-all duration-500 hover:-translate-y-1 hover:border-primary/30 hover:shadow-card"
          :style="{ transitionDelay: `${idx * 80}ms` }"
          :disabled="enrolling === course.course_id"
          @click="selectCourse(course)"
        >
          <!-- Corner glow -->
          <div class="absolute -right-8 -bottom-8 h-32 w-32 rounded-full bg-primary/5 blur-2xl opacity-0 transition-opacity duration-500 group-hover:opacity-100" />

          <!-- Header row -->
          <div class="relative mb-4 flex items-center justify-between">
            <div class="flex h-12 w-12 items-center justify-center rounded-2xl bg-space-surface text-2xl transition-colors duration-300 group-hover:bg-card-hover">
              {{ course.icon || "📚" }}
            </div>
            <span class="rounded-full border border-subtle bg-space-surface/50 px-2.5 py-1 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
              {{ course.node_count || "?" }} 节点
            </span>
          </div>

          <!-- Title -->
          <h3 class="relative text-lg font-bold tracking-tight">{{ course.title_cn }}</h3>
          <p class="relative mt-2 line-clamp-2 text-sm font-light leading-relaxed text-text-secondary">
            {{ course.description_cn }}
          </p>

          <!-- Difficulty stars -->
          <div class="relative mt-3 flex items-center gap-1">
            <span
              v-for="s in 5"
              :key="s"
              class="text-xs"
              :class="s <= Math.ceil(course.difficulty * 5) ? 'text-warning' : 'text-text-muted/30'"
            >★</span>
            <span class="ml-2 text-[11px] font-medium text-text-muted">
              {{ course.estimated_hours }}h
            </span>
          </div>

          <!-- Tags -->
          <div class="relative mt-4 flex flex-wrap gap-1.5">
            <span
              v-for="tag in course.tags?.slice(0, 4)"
              :key="tag"
              class="rounded-full border border-subtle bg-space-surface/50 px-2.5 py-1 text-[10px] font-medium text-text-muted transition-colors group-hover:border-hover group-hover:text-text-secondary"
            >{{ tag }}</span>
          </div>

          <!-- Enrolled badge -->
          <div v-if="isEnrolled(course.course_id)" class="relative mt-4 rounded-xl border border-success/20 bg-success-soft px-3 py-2 text-center text-[11px] font-semibold text-success">
            已注册 · {{ course.progress ? Math.round(course.progress * 100) : 0 }}% 完成
          </div>

          <!-- Selecting indicator -->
          <div v-if="enrolling === course.course_id" class="relative mt-4 flex items-center justify-center gap-2 text-xs text-primary">
            <span class="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
            正在初始化...
          </div>
        </button>
      </div>

      <!-- Back to home -->
      <div class="mt-12 text-center">
        <button
          type="button"
          class="text-xs text-text-muted underline underline-offset-4 transition-colors hover:text-primary"
          @click="$emit('go-home')"
        >
          返回首页
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  courses: { type: Array, default: () => [] },
  enrolled: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
});

const emit = defineEmits(["select", "go-home"]);

const searchQuery = ref("");
const enrolling = ref(null);
const debouncedSearch = ref("");

let debounceTimer = null;
function onSearchInput() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    debouncedSearch.value = searchQuery.value.trim();
  }, 200);
}

const filteredCourses = computed(() => {
  const q = debouncedSearch.value.toLowerCase();
  if (!q) return props.courses;
  return props.courses.filter(c =>
    c.title_cn?.toLowerCase().includes(q) ||
    c.title?.toLowerCase().includes(q) ||
    (c.tags || []).some(t => t.toLowerCase().includes(q))
  );
});

function isEnrolled(courseId) {
  return props.enrolled.some(c => c.course_id === courseId);
}

async function selectCourse(course) {
  enrolling.value = course.course_id;
  try {
    emit("select", course.course_id);
  } finally {
    // enrolling cleared by parent re-render
  }
}

// Clear enrolling state when courses/loading change
watch([() => props.courses, () => props.loading], () => {
  enrolling.value = null;
});
</script>
