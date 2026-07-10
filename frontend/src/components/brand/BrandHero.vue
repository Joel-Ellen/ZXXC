<template>
  <section class="brand-hero" aria-labelledby="brand-hero-title">
    <img
      class="brand-hero__image"
      src="/brand/workspace-preview.png"
      alt="EduAgent 工作台截图，展示学习驾驶舱、能力反馈和学习托盘。"
      decoding="async"
      fetchpriority="high"
    />

    <div class="brand-hero__content">
      <p class="brand-hero__kicker">自适应算法学习工作台</p>
      <h1 id="brand-hero-title">EduAgent 智能学习工作台</h1>
      <p class="brand-hero__copy">
        把冷启动测评、知识路径、对话辅导和能力反馈放在同一个学习现场，让下一步不再靠猜。
      </p>
      <div class="brand-hero__actions" aria-label="主要操作">
        <RouterLink class="brand-hero__primary focus-ring" to="/app">
          进入工作台
        </RouterLink>
        <a class="brand-hero__secondary focus-ring" href="#evidence">
          查看学习证据
        </a>
      </div>
    </div>
  </section>
</template>

<script setup>
import { RouterLink } from "vue-router";
</script>

<style scoped>
.brand-hero {
  position: relative;
  display: flex;
  align-items: flex-end;
  min-height: clamp(38rem, 84dvh, 46rem);
  overflow: hidden;
  background: var(--space-bg);
  isolation: isolate;
}

.brand-hero__image {
  position: absolute;
  inset: 0;
  z-index: -2;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 58% 10%;
}

.brand-hero::before,
.brand-hero::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.brand-hero::before {
  z-index: -1;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--space-bg) 96%, transparent) 0%, color-mix(in srgb, var(--space-bg) 78%, transparent) 39%, color-mix(in srgb, var(--space-bg) 20%, transparent) 74%, transparent 100%),
    linear-gradient(180deg, color-mix(in srgb, var(--space-bg) 72%, transparent) 0%, transparent 28%, color-mix(in srgb, var(--space-bg) 68%, transparent) 100%);
}

.brand-hero::after {
  z-index: -1;
  background: radial-gradient(circle at 18% 78%, color-mix(in srgb, var(--color-primary) 18%, transparent), transparent 34rem);
}

.brand-hero__content {
  width: min(100% - 2rem, 1180px);
  margin: 0 auto;
  padding: 7.75rem 0 clamp(4.5rem, 9vw, 7rem);
}

.brand-hero__kicker {
  width: fit-content;
  margin: 0 0 1.1rem;
  padding: 0.48rem 0.78rem;
  border: 1px solid color-mix(in srgb, var(--color-primary) 30%, var(--border-subtle));
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--color-primary-soft) 76%, var(--space-bg));
  color: var(--color-primary-dark);
  font-size: 0.84rem;
  font-weight: 800;
}

.brand-hero h1 {
  max-width: 13.5ch;
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(3.1rem, 7.2vw, 5.4rem);
  font-weight: 900;
  line-height: 0.98;
  letter-spacing: 0;
}

.brand-hero__copy {
  max-width: 39rem;
  margin: 1.5rem 0 0;
  color: color-mix(in srgb, var(--text-secondary) 88%, var(--text-primary));
  font-size: clamp(1.05rem, 1.5vw, 1.25rem);
  line-height: 1.72;
}

.brand-hero__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.85rem;
  margin-top: 2rem;
}

.brand-hero__primary,
.brand-hero__secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 3rem;
  padding: 0 1.3rem;
  border-radius: var(--radius-pill);
  font-size: 0.95rem;
  font-weight: 850;
  text-decoration: none;
  white-space: nowrap;
  transition:
    transform var(--duration-fast) var(--ease-standard),
    background var(--duration-fast) var(--ease-standard),
    border-color var(--duration-fast) var(--ease-standard);
}

.brand-hero__primary {
  background: var(--text-primary);
  color: var(--space-bg);
}

.brand-hero__secondary {
  border: 1px solid color-mix(in srgb, var(--border-strong) 74%, transparent);
  background: color-mix(in srgb, var(--space-panel) 74%, transparent);
  color: var(--text-primary);
}

.brand-hero__primary:hover,
.brand-hero__secondary:hover {
  transform: translateY(-1px);
}

.brand-hero__primary:hover {
  background: var(--color-primary);
  color: var(--color-primary-text);
}

.brand-hero__secondary:hover {
  border-color: color-mix(in srgb, var(--color-primary) 34%, var(--border-strong));
  background: var(--space-panel);
}

.brand-hero__primary:active,
.brand-hero__secondary:active {
  transform: translateY(0);
}

:global([data-theme="dark"]) .brand-hero::before {
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--space-bg) 98%, transparent) 0%, color-mix(in srgb, var(--space-bg) 82%, transparent) 42%, color-mix(in srgb, var(--space-bg) 24%, transparent) 76%, transparent 100%),
    linear-gradient(180deg, color-mix(in srgb, var(--space-bg) 78%, transparent) 0%, transparent 32%, color-mix(in srgb, var(--space-bg) 78%, transparent) 100%);
}

:global([data-theme="dark"]) .brand-hero__kicker {
  color: var(--color-primary-dark);
}

@media (max-width: 860px) {
  .brand-hero {
    min-height: 43rem;
  }

  .brand-hero__image {
    object-position: 64% 12%;
  }

  .brand-hero::before {
    background:
      linear-gradient(180deg, color-mix(in srgb, var(--space-bg) 92%, transparent) 0%, color-mix(in srgb, var(--space-bg) 76%, transparent) 54%, color-mix(in srgb, var(--space-bg) 44%, transparent) 100%),
      linear-gradient(90deg, color-mix(in srgb, var(--space-bg) 88%, transparent), transparent 100%);
  }

  .brand-hero__content {
    width: min(100% - 1.25rem, 1180px);
    padding-top: 6.25rem;
  }

  .brand-hero h1 {
    max-width: 9ch;
    font-size: clamp(2.8rem, 13vw, 4.15rem);
  }

  .brand-hero__copy {
    max-width: 31rem;
    font-size: 1rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .brand-hero__primary,
  .brand-hero__secondary {
    transition: none;
  }
}
</style>
