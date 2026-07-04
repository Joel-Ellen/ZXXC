<template>
  <section class="relative z-10 min-h-screen px-4 py-6 sm:px-6 lg:px-8">
    <div class="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <header class="workspace-shell-card rounded-2xl px-5 py-5 sm:px-6">
        <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div class="min-w-0">
            <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">课程目录</p>
            <h1 class="mt-2 text-[30px] font-black tracking-tight text-text-primary">选择下一门要学的课程</h1>
            <p class="mt-3 max-w-3xl text-sm leading-7 text-text-secondary">
              先筛选、再选择课程，接着进入整页问卷。这里不直接 enroll，避免课程画像信息丢失。
            </p>
          </div>

          <button
            type="button"
            class="workspace-shell-btn focus-ring px-4 py-2.5 text-sm font-semibold"
            @click="$emit('back')"
          >
            返回课程管理
          </button>
        </div>
      </header>

      <section class="workspace-shell-card rounded-2xl px-5 py-5 sm:px-6">
        <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_240px]">
          <label class="min-w-0">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">搜索</span>
            <input
              :value="filters.search"
              type="text"
              placeholder="搜索课程名称、标签或方向"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary placeholder:text-text-muted"
              @input="$emit('update-search', $event.target.value)"
            />
          </label>

          <label>
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">分类</span>
            <select
              :value="filters.category"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @change="$emit('update-category', $event.target.value)"
            >
              <option value="all">全部分类</option>
              <option v-for="category in categories" :key="category" :value="category">{{ category }}</option>
            </select>
          </label>
        </div>
      </section>

      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="course in courses"
          :key="course.course_id"
          class="workspace-shell-card rounded-2xl px-5 py-5"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-center gap-3">
              <div class="flex h-12 w-12 items-center justify-center rounded-2xl border border-subtle bg-space-elevated text-2xl">
                {{ course.icon || "📘" }}
              </div>
              <div class="min-w-0">
                <h2 class="truncate text-lg font-black tracking-tight text-text-primary">{{ course.title_cn }}</h2>
                <p class="text-xs text-text-muted">{{ course.category }}</p>
              </div>
            </div>
            <span class="workspace-shell-chip px-3 py-1 text-[11px] font-semibold">{{ course.node_count || 0 }} 节点</span>
          </div>

          <p class="mt-4 text-sm leading-7 text-text-secondary">{{ course.description_cn }}</p>

          <div class="mt-4 flex flex-wrap gap-2">
            <span
              v-for="tag in (course.tags || []).slice(0, 4)"
              :key="tag"
              class="workspace-shell-chip px-3 py-1 text-[11px] text-text-secondary"
            >
              {{ tag }}
            </span>
          </div>

          <div class="mt-5 grid gap-3 sm:grid-cols-2">
            <div class="workspace-shell-card-soft rounded-2xl px-4 py-3">
              <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">难度</p>
              <p class="mt-2 text-sm font-semibold text-text-primary">{{ Math.round((course.difficulty || 0) * 100) }} / 100</p>
            </div>
            <div class="workspace-shell-card-soft rounded-2xl px-4 py-3">
              <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">预计学时</p>
              <p class="mt-2 text-sm font-semibold text-text-primary">{{ course.estimated_hours || 0 }} 小时</p>
            </div>
          </div>

          <div class="mt-5 flex items-center justify-between gap-3">
            <span class="text-xs text-text-muted">
              {{ enrolledIds.includes(course.course_id) ? "已在学习列表中" : "选择后进入问卷" }}
            </span>
            <button
              type="button"
              class="workspace-shell-btn workspace-shell-btn--accent focus-ring px-4 py-2.5 text-sm font-semibold"
              :disabled="busy"
              @click="$emit('select-course', course)"
            >
              {{ enrolledIds.includes(course.course_id) ? "重新画像" : "选择课程" }}
            </button>
          </div>
        </article>
      </section>
    </div>
  </section>
</template>

<script setup>
defineProps({
  courses: { type: Array, default: () => [] },
  categories: { type: Array, default: () => [] },
  filters: { type: Object, required: true },
  enrolledIds: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
});

defineEmits(["back", "update-search", "update-category", "select-course"]);
</script>
