<template>
  <div class="brand-page">
    <BrandTopNav />

    <main>
      <BrandHero />

      <section id="evidence" class="brand-placeholder" aria-labelledby="evidence-title">
        <div class="brand-placeholder__inner">
          <p class="brand-placeholder__label">学习证据区</p>
          <h2 id="evidence-title">这里会承接真实截图、学习反馈和能力变化。</h2>
          <p>
            下一批再补完整证据区。现在先保留页面节奏，让首屏截图、标题层级和 CTA 的视觉基准稳定下来。
          </p>
        </div>
      </section>

      <section id="flow" class="brand-placeholder brand-placeholder--quiet" aria-labelledby="flow-title">
        <div class="brand-placeholder__inner">
          <p class="brand-placeholder__label">流程区</p>
          <h2 id="flow-title">这里会解释从测评到路径再到辅导的学习闭环。</h2>
          <p>
            流程区暂时只占位，不展开完整内容，避免在首屏视觉方向确定前把页面做散。
          </p>
        </div>
      </section>

      <BrandCTASection />
    </main>
  </div>
</template>

<script setup>
import BrandCTASection from "../components/brand/BrandCTASection.vue";
import BrandHero from "../components/brand/BrandHero.vue";
import BrandTopNav from "../components/brand/BrandTopNav.vue";
</script>

<style scoped>
.brand-page {
  min-height: 100dvh;
  background: var(--space-bg);
  color: var(--text-primary);
  font-family: var(--font-sans);
}

.brand-placeholder {
  border-top: 1px solid var(--border-subtle);
  background: var(--space-surface);
}

.brand-placeholder--quiet {
  background: var(--space-bg);
}

.brand-placeholder__inner {
  width: min(100% - 2rem, 1180px);
  margin: 0 auto;
  padding: clamp(4.5rem, 9vw, 7rem) 0;
}

.brand-placeholder__label {
  margin: 0 0 0.9rem;
  color: var(--color-primary-dark);
  font-size: 0.9rem;
  font-weight: 800;
}

.brand-placeholder h2 {
  max-width: 15ch;
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(2.1rem, 5vw, 4rem);
  font-weight: 900;
  line-height: 1.06;
  letter-spacing: 0;
}

.brand-placeholder p:not(.brand-placeholder__label) {
  max-width: 44rem;
  margin: 1.25rem 0 0;
  color: var(--text-secondary);
  font-size: 1rem;
  line-height: 1.75;
}

@media (max-width: 760px) {
  .brand-placeholder__inner {
    width: min(100% - 1.25rem, 1180px);
  }
}
</style>
