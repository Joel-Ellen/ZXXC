<template>
  <header class="brand-nav">
    <div class="brand-nav__inner">
      <RouterLink class="brand-nav__mark focus-ring" to="/" aria-label="EduAgent 首页">
        <span class="brand-nav__logo">EA</span>
        <span class="brand-nav__name">EduAgent</span>
      </RouterLink>

      <nav class="brand-nav__links" aria-label="品牌页导航">
        <a href="#evidence">学习证据</a>
        <a href="#flow">学习流程</a>
        <a href="#start">开始使用</a>
      </nav>

      <RouterLink class="brand-nav__cta focus-ring" to="/app">
        进入工作台
      </RouterLink>
    </div>
  </header>
</template>

<script setup>
import { RouterLink } from "vue-router";
</script>

<style scoped>
.brand-nav {
  position: fixed;
  z-index: var(--z-sticky);
  inset: 0 0 auto;
  border-bottom: 1px solid color-mix(in srgb, var(--border-subtle) 74%, transparent);
  background: color-mix(in srgb, var(--space-bg) 86%, transparent);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}

.brand-nav__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: clamp(1rem, 3vw, 2.5rem);
  width: min(100% - 2rem, 1180px);
  min-height: 4.5rem;
  margin: 0 auto;
}

.brand-nav__mark,
.brand-nav__cta {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
  white-space: nowrap;
}

.brand-nav__mark {
  gap: 0.7rem;
  color: var(--text-primary);
}

.brand-nav__logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: var(--radius-pill);
  background: var(--color-primary);
  color: var(--color-primary-text);
  font-size: 0.72rem;
  font-weight: 800;
}

.brand-nav__name {
  font-size: 0.98rem;
  font-weight: 800;
}

.brand-nav__links {
  display: flex;
  align-items: center;
  gap: clamp(1rem, 2.6vw, 2rem);
  font-size: 0.9rem;
  font-weight: 650;
  color: color-mix(in srgb, var(--text-secondary) 84%, transparent);
}

.brand-nav__links a {
  color: inherit;
  text-decoration: none;
  transition: color var(--duration-fast) var(--ease-standard);
}

.brand-nav__links a:hover {
  color: var(--text-primary);
}

.brand-nav__cta {
  min-height: 2.35rem;
  padding: 0 1.05rem;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  background: var(--text-primary);
  color: var(--space-bg);
  font-size: 0.86rem;
  font-weight: 800;
  transition:
    transform var(--duration-fast) var(--ease-standard),
    background var(--duration-fast) var(--ease-standard);
}

.brand-nav__cta:hover {
  transform: translateY(-1px);
  background: var(--color-primary);
  color: var(--color-primary-text);
}

.brand-nav__cta:active {
  transform: translateY(0);
}

@media (max-width: 760px) {
  .brand-nav__inner {
    width: min(100% - 1.25rem, 1180px);
    min-height: 4rem;
  }

  .brand-nav__links {
    display: none;
  }

  .brand-nav__name {
    font-size: 0.92rem;
  }

  .brand-nav__cta {
    min-height: 2.25rem;
    padding-inline: 0.85rem;
    font-size: 0.8rem;
  }
}
</style>
