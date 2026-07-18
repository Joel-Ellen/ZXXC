<template>
  <div class="min-h-screen bg-space-bg text-text-primary">
    <header class="relative z-20 border-b border-subtle bg-space-panel px-4 py-3 sm:px-6">
      <div class="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3">
        <RouterLink :to="{ name: 'app-workspace' }" class="app-brand-link flex items-center gap-2 font-black text-text-primary">
          <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-soft text-xs text-primary">EA</span>
          <span>EduAgent</span>
        </RouterLink>

        <nav class="flex flex-wrap items-center gap-1 text-sm" aria-label="Primary navigation">
          <RouterLink :to="{ name: 'app-workspace' }" class="route-nav-link">学习</RouterLink>
          <RouterLink :to="{ name: 'courses' }" class="route-nav-link">课程</RouterLink>
          <RouterLink :to="{ name: 'progress' }" class="route-nav-link">进度</RouterLink>
          <RouterLink :to="{ name: 'review' }" class="route-nav-link">复习</RouterLink>
          <RouterLink :to="{ name: 'settings' }" class="route-nav-link">设置</RouterLink>
          <RouterLink :to="{ name: 'account' }" class="route-nav-link">账户</RouterLink>
        </nav>
      </div>
    </header>

    <main class="relative z-10">
      <slot />
    </main>
  </div>
</template>

<script setup>
import { RouterLink } from "vue-router";
</script>

<style scoped>
.app-brand-link,
.route-nav-link {
  min-height: 2.75rem;
}

.route-nav-link {
  display: inline-flex;
  align-items: center;
  border-radius: 0.5rem;
  color: var(--text-secondary);
  padding: 0.45rem 0.65rem;
}

.route-nav-link:hover,
.route-nav-link.router-link-active {
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
}
</style>
