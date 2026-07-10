<template>
  <section id="start" class="brand-cta" aria-labelledby="brand-cta-title">
    <div class="brand-cta__inner">
      <div>
        <p class="brand-cta__label">准备开始</p>
        <h2 id="brand-cta-title">把下一步学习变清楚。</h2>
      </div>
      <p>
        进入工作台后，系统会从登录、选课、冷启动测评开始，把路径、资源和反馈逐步接到同一条学习线上。
      </p>
      <RouterLink class="brand-cta__button focus-ring" to="/app">
        进入工作台
      </RouterLink>
    </div>
  </section>
</template>

<script setup>
import { RouterLink } from "vue-router";
</script>

<style scoped>
.brand-cta {
  border-top: 1px solid var(--border-subtle);
  background:
    radial-gradient(circle at 12% 18%, color-mix(in srgb, var(--color-primary-soft) 78%, transparent), transparent 24rem),
    var(--space-elevated);
}

.brand-cta__inner {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(18rem, 0.75fr) auto;
  align-items: center;
  gap: clamp(1.5rem, 4vw, 3.5rem);
  width: min(100% - 2rem, 1180px);
  margin: 0 auto;
  padding: clamp(4rem, 9vw, 6.5rem) 0;
}

.brand-cta__label {
  margin: 0 0 0.85rem;
  color: var(--color-primary-dark);
  font-size: 0.9rem;
  font-weight: 800;
}

.brand-cta h2 {
  max-width: 12ch;
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(2.4rem, 5vw, 4.5rem);
  font-weight: 900;
  line-height: 1;
  letter-spacing: 0;
}

.brand-cta p:not(.brand-cta__label) {
  max-width: 34rem;
  margin: 0;
  color: var(--text-secondary);
  font-size: 1rem;
  line-height: 1.75;
}

.brand-cta__button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 3rem;
  padding: 0 1.3rem;
  border-radius: var(--radius-pill);
  background: var(--text-primary);
  color: var(--space-bg);
  font-size: 0.95rem;
  font-weight: 850;
  text-decoration: none;
  white-space: nowrap;
  transition:
    transform var(--duration-fast) var(--ease-standard),
    background var(--duration-fast) var(--ease-standard);
}

.brand-cta__button:hover {
  transform: translateY(-1px);
  background: var(--color-primary);
  color: var(--color-primary-text);
}

.brand-cta__button:active {
  transform: translateY(0);
}

@media (max-width: 900px) {
  .brand-cta__inner {
    grid-template-columns: 1fr;
    width: min(100% - 1.25rem, 1180px);
  }

  .brand-cta__button {
    width: fit-content;
  }
}
</style>
