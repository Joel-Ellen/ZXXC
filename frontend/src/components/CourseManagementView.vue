<template>
  <section class="relative z-10 min-h-screen px-4 py-6 sm:px-6 lg:px-8">
    <div class="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <header class="workspace-shell-card rounded-2xl px-5 py-5 sm:px-6">
        <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div class="min-w-0">
            <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">课程管理</p>
            <h1 class="mt-2 text-[30px] font-black tracking-tight text-text-primary">先从你的课程开始</h1>
            <p class="mt-3 max-w-3xl text-sm leading-7 text-text-secondary">
              登录后默认进入课程管理。这里集中处理当前学习课程、进入工作台、新增课程和删除课程，不把这些操作散落到学习页里。
            </p>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <button
              type="button"
              class="workspace-shell-btn focus-ring px-4 py-2.5 text-sm font-semibold"
              @click="$emit('open-settings')"
            >
              用户管理
            </button>
            <button
              type="button"
              class="workspace-shell-btn workspace-shell-btn--accent focus-ring px-4 py-2.5 text-sm font-semibold"
              @click="$emit('open-catalog')"
            >
              新增课程
            </button>
          </div>
        </div>
      </header>

      <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section class="space-y-4">
          <div v-if="courses.length" class="grid gap-4 md:grid-cols-2">
            <article
              v-for="course in courses"
              :key="course.course_id"
              class="workspace-shell-card card-hover course-card rounded-2xl px-5 py-5"
            >
              <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                  <div class="flex items-center gap-3">
                    <div class="flex h-12 w-12 items-center justify-center rounded-2xl border border-subtle bg-space-elevated text-2xl">
                      {{ course.icon || "📘" }}
                    </div>
                    <div class="min-w-0">
                      <h2 class="truncate text-lg font-black tracking-tight text-text-primary">{{ course.title_cn }}</h2>
                      <p class="text-xs text-text-muted">{{ course.category || "未分类" }}</p>
                    </div>
                  </div>
                  <p class="mt-4 text-sm leading-7 text-text-secondary">{{ course.description_cn }}</p>
                </div>

                <span
                  class="workspace-shell-chip px-3 py-1 text-[11px] font-semibold"
                  :class="course.course_id === activeCourse?.course_id ? 'workspace-shell-chip--accent' : ''"
                >
                  {{ course.course_id === activeCourse?.course_id ? "当前课程" : "已选课程" }}
                </span>
              </div>

              <div class="mt-5">
                <div class="mb-2 flex items-center justify-between text-[11px] font-semibold text-text-muted">
                  <span>学习进度</span>
                  <span>{{ Math.round((course.progress || 0) * 100) }}%</span>
                </div>
                <div class="h-2 overflow-hidden rounded-full bg-space-elevated">
                  <div
                    class="h-full rounded-full bg-gradient-to-r from-primary to-secondary shadow-[0_0_16px_var(--color-primary-soft)] transition-all duration-500"
                    :style="{ width: `${Math.max(4, Math.round((course.progress || 0) * 100))}%` }"
                  />
                </div>
              </div>

              <div class="mt-5 grid gap-3 sm:grid-cols-3">
                <div class="workspace-shell-card-soft rounded-2xl px-4 py-3">
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">进度</p>
                  <p class="mt-2 text-xl font-black text-text-primary">{{ Math.round((course.progress || 0) * 100) }}%</p>
                </div>
                <div class="workspace-shell-card-soft rounded-2xl px-4 py-3">
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">节点</p>
                  <p class="mt-2 text-xl font-black text-text-primary">{{ course.completed_nodes || 0 }}</p>
                </div>
                <div class="workspace-shell-card-soft rounded-2xl px-4 py-3">
                  <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">预计学时</p>
                  <p class="mt-2 text-xl font-black text-text-primary">{{ course.estimated_hours || 0 }}h</p>
                </div>
              </div>

              <div class="mt-5 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  class="btn-primary focus-ring px-4 py-2.5 text-sm font-semibold"
                  :disabled="busy"
                  @click="$emit('enter-course', course.course_id)"
                >
                  进入课程
                </button>
                <button
                  type="button"
                  class="workspace-shell-btn focus-ring px-4 py-2.5 text-sm font-semibold"
                  :disabled="busy"
                  @click="$emit('open-catalog')"
                >
                  再加一门
                </button>
                <button
                  type="button"
                  class="workspace-shell-btn workspace-shell-btn--danger focus-ring px-4 py-2.5 text-sm font-semibold"
                  :disabled="busy"
                  @click="requestDelete(course)"
                >
                  删除课程
                </button>
              </div>
            </article>
          </div>

          <div v-else class="workspace-shell-card rounded-2xl px-6 py-12 text-center">
            <div class="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-subtle bg-space-elevated text-3xl">
              ＋
            </div>
            <h2 class="mt-5 text-xl font-black tracking-tight text-text-primary">你还没有正在学习的课程</h2>
            <p class="mx-auto mt-3 max-w-xl text-sm leading-7 text-text-secondary">
              先从课程目录里添加一门课程。添加后会进入整页问卷，系统会根据你的背景、目标和学习偏好初始化课程画像。
            </p>
            <button
              type="button"
              class="btn-primary focus-ring mt-6 px-4 py-2.5 text-sm font-semibold"
              @click="$emit('open-catalog')"
            >
              去添加课程
            </button>
          </div>
        </section>

        <aside class="space-y-4">
          <section class="workspace-shell-card rounded-2xl px-5 py-5">
            <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">当前用户</p>
            <h2 class="mt-2 text-lg font-black tracking-tight text-text-primary">
              {{ user?.display_name || user?.user_id || "未命名用户" }}
            </h2>
            <p class="mt-2 text-sm text-text-secondary">{{ user?.email || "暂无邮箱" }}</p>

            <div class="mt-5 space-y-3">
              <div class="workspace-shell-card-soft rounded-2xl px-4 py-3">
                <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">学习目标</p>
                <p class="mt-2 text-sm leading-6 text-text-secondary">{{ profile?.learning_goal || "尚未填写" }}</p>
              </div>
              <div class="workspace-shell-card-soft rounded-2xl px-4 py-3">
                <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">每周投入</p>
                <p class="mt-2 text-sm leading-6 text-text-secondary">{{ profile?.weekly_study_hours || 0 }} 小时</p>
              </div>
            </div>
          </section>

          <section class="workspace-shell-card rounded-2xl px-5 py-5">
            <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">操作说明</p>
            <ul class="mt-3 space-y-3 text-sm leading-6 text-text-secondary">
              <li>进入课程后才会挂载学习工作台，离开后会硬性销毁工作台实例。</li>
              <li>删除课程会删除该课程下的学习状态、课程画像和选课关系。</li>
              <li>用户资料会作为新增课程问卷的默认值，减少重复填写。</li>
            </ul>
          </section>
        </aside>
      </div>
    </div>

    <div
      v-if="pendingDelete"
      class="fixed inset-0 z-40 flex items-center justify-center bg-[rgba(15,23,42,0.3)] px-4 backdrop-blur-sm"
    >
      <div class="workspace-shell-card w-full max-w-lg rounded-2xl px-6 py-6">
        <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">确认删除</p>
        <h3 class="mt-2 text-xl font-black tracking-tight text-text-primary">删除 {{ pendingDelete.title_cn }}？</h3>
        <p class="mt-3 text-sm leading-7 text-text-secondary">
          这会彻底删除这门课程下的学习状态、课程画像和选课关系。全局账号资料不会被删除。
        </p>

        <div class="mt-6 flex justify-end gap-2">
          <button
            type="button"
            class="workspace-shell-btn focus-ring px-4 py-2.5 text-sm font-semibold"
            @click="pendingDelete = null"
          >
            取消
          </button>
          <button
            type="button"
            class="workspace-shell-btn workspace-shell-btn--danger focus-ring px-4 py-2.5 text-sm font-semibold"
            :disabled="busy"
            @click="confirmDelete"
          >
            确认删除
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";

const props = defineProps({
  user: { type: Object, default: null },
  profile: { type: Object, default: null },
  courses: { type: Array, default: () => [] },
  activeCourse: { type: Object, default: null },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits(["open-catalog", "open-settings", "enter-course", "delete-course"]);

const pendingDelete = ref(null);

function requestDelete(course) {
  pendingDelete.value = course;
}

function confirmDelete() {
  if (!pendingDelete.value) {
    return;
  }
  emit("delete-course", pendingDelete.value.course_id);
  pendingDelete.value = null;
}
</script>
