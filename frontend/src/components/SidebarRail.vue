<template>
  <aside class="z-50 hidden h-full w-[96px] shrink-0 px-3 py-4 xl:flex" aria-label="内容分类导航">
    <div
      class="rail-shell relative flex h-full w-full flex-col items-center overflow-visible px-2 py-4 transition-all duration-300 rounded-2xl"
    >
      <!-- Brand mark -->
      <div class="rail-brand relative z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-xl mb-1">
        <span class="text-[13px] font-black tracking-[0.10em] text-primary-dark">EA</span>
      </div>

      <div class="rail-divider relative z-10 my-3 h-px w-8" />

      <!-- Content category navigation -->
      <nav class="relative z-10 flex w-full flex-col items-center gap-2" aria-label="内容分类">
        <button
          v-for="item in contentItems"
          :key="item.key"
          type="button"
          class="focus-ring rail-nav-btn group relative flex h-[52px] w-[52px] shrink-0 flex-col items-center justify-center gap-0.5 rounded-xl transition-all duration-200"
          :class="item.key === activePanel ? 'rail-nav-btn--active' : 'rail-nav-btn--idle'"
          :style="item.key === activePanel ? `--rail-accent: ${item.color}` : ''"
          :aria-label="item.label"
          :aria-pressed="String(item.key === activePanel)"
          :title="item.label"
          @click="$emit('select', item.key)"
        >
          <component :is="item.icon" :size="18" />
          <span class="text-[8px] font-bold tracking-[0.08em] uppercase leading-none opacity-70 mt-0.5">
            {{ item.short }}
          </span>

          <!-- Tooltip -->
          <span class="rail-tooltip pointer-events-none absolute left-[calc(100%+12px)] top-1/2 z-50 flex -translate-y-1/2 items-center gap-2.5 whitespace-nowrap rounded-xl px-3 py-2 text-left opacity-0 shadow-[0_12px_32px_rgba(0,107,173,0.12)] transition-all duration-200 group-hover:translate-x-0.5 group-hover:opacity-100">
            <span class="flex h-7 w-7 items-center justify-center rounded-lg text-sm"
                  :style="{ background: item.softColor, color: item.color }">
              <component :is="item.icon" :size="14" />
            </span>
            <span>
              <span class="block text-[9px] font-black uppercase tracking-[0.14em] text-text-muted">{{ item.short }}</span>
              <span class="mt-0.5 block text-xs font-semibold text-text-primary">{{ item.label }}</span>
            </span>
          </span>
        </button>
      </nav>

      <div class="rail-divider relative z-10 my-3 h-px w-8" />

      <!-- Path nav -->
      <button
        type="button"
        class="focus-ring rail-nav-btn group relative flex h-[52px] w-[52px] shrink-0 flex-col items-center justify-center gap-0.5 rounded-xl transition-all duration-200"
        :class="activePanel === 'tree' ? 'rail-nav-btn--active' : 'rail-nav-btn--idle'"
        aria-label="知识路径"
        :aria-pressed="String(activePanel === 'tree')"
        title="知识路径"
        @click="$emit('select', 'tree')"
      >
        <IconTree :size="18" />
        <span class="text-[8px] font-bold tracking-[0.08em] uppercase leading-none opacity-70 mt-0.5">PATH</span>
        <span
          v-if="pathCount"
          class="rail-nav-btn__badge absolute -right-1 -top-1 flex h-4.5 min-w-[18px] items-center justify-center rounded-full px-1 text-[9px] font-black leading-none"
        >
          {{ pathCount }}
        </span>
        <!-- Tooltip -->
        <span class="rail-tooltip pointer-events-none absolute left-[calc(100%+12px)] top-1/2 z-50 flex -translate-y-1/2 items-center gap-2.5 whitespace-nowrap rounded-xl px-3 py-2 text-left opacity-0 shadow-[0_12px_32px_rgba(0,107,173,0.12)] transition-all duration-200 group-hover:translate-x-0.5 group-hover:opacity-100">
          <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-soft text-primary-dark">
            <IconTree :size="14" />
          </span>
          <span>
            <span class="block text-[9px] font-black uppercase tracking-[0.14em] text-text-muted">KNOWLEDGE</span>
            <span class="mt-0.5 block text-xs font-semibold text-text-primary">知识路径</span>
          </span>
        </span>
      </button>

      <button
        type="button"
        class="focus-ring rail-nav-btn rail-nav-btn--idle group relative mt-2 flex h-[52px] w-[52px] shrink-0 flex-col items-center justify-center gap-0.5 rounded-xl transition-all duration-200"
        aria-label="重新测试"
        title="重新测试"
        @click="$emit('select', 'probe')"
      >
        <IconQuiz :size="18" />
        <span class="mt-0.5 text-[8px] font-bold leading-none opacity-70">测试</span>
        <span class="rail-tooltip pointer-events-none absolute left-[calc(100%+12px)] top-1/2 z-50 -translate-y-1/2 whitespace-nowrap rounded-xl px-3 py-2 text-xs font-semibold text-text-primary opacity-0 transition-all duration-200 group-hover:translate-x-0.5 group-hover:opacity-100">
          重新进行入学测试
        </span>
      </button>

      <!-- Bottom stats -->
      <div class="relative z-10 mt-auto flex w-[52px] shrink-0 flex-col items-center rounded-xl border border-subtle bg-space-elevated px-1 py-2.5 text-center">
        <span class="text-[8px] font-black uppercase tracking-[0.14em] text-text-muted">节点</span>
        <span class="mt-1.5 text-[22px] font-black leading-none text-text-primary">{{ pathCount }}</span>
        <span class="mt-1.5 h-1.5 w-1.5 rounded-full bg-success shadow-[0_0_8px_var(--color-success)]" role="status" aria-label="就绪" />
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed } from "vue";
import IconChat from "./icons/IconChat.vue";
import IconCheck from "./icons/IconCheck.vue";
import IconDoc from "./icons/IconDoc.vue";
import IconExpand from "./icons/IconExpand.vue";
import IconQuiz from "./icons/IconQuiz.vue";
import IconTree from "./icons/IconTree.vue";

defineProps({
  activePanel:  { type: String, default: "concept" },
  drawerOpen:   { type: Boolean, default: false },
  panelId:      { type: String, default: "workspace-sidebar-drawer" },
  pathCount:    { type: Number, default: 0 },
});

defineEmits(["select"]);

const contentItems = computed(() => [
  {
    key: "concept",
    short: "概念",
    label: "概念导图",
    icon: IconDoc,
    color: "var(--learning-concept-dark)",
    softColor: "var(--learning-concept-soft)",
  },
  {
    key: "code",
    short: "代码",
    label: "代码示例",
    icon: IconExpand,
    color: "var(--learning-code-dark)",
    softColor: "var(--learning-code-soft)",
  },
  {
    key: "practice",
    short: "练习",
    label: "互动练习",
    icon: IconCheck,
    color: "var(--learning-practice-dark)",
    softColor: "var(--learning-practice-soft)",
  },
  {
    key: "video",
    short: "视频",
    label: "视频摘要",
    icon: IconChat,
    color: "var(--learning-video-dark)",
    softColor: "var(--learning-video-soft)",
  },
  {
    key: "quiz",
    short: "测验",
    label: "诊断测验",
    icon: IconQuiz,
    color: "var(--learning-quiz-dark)",
    softColor: "var(--learning-quiz-soft)",
  },
]);
</script>

<style scoped>
.rail-shell {
  border-radius: var(--radius-sm) !important;
  border: 1px solid var(--border-subtle);
  background: var(--space-panel);
  box-shadow: var(--workspace-shadow-soft);
}

.rail-brand {
  border-radius: var(--radius-sm) !important;
  border: 1px solid color-mix(in srgb, var(--color-primary) 22%, var(--border-subtle));
  background: color-mix(in srgb, var(--color-primary-soft) 80%, white);
  color: var(--color-primary-dark);
}

.rail-divider {
  background: linear-gradient(90deg, transparent, var(--border-strong), transparent);
}

/* nav buttons */
.rail-nav-btn {
  border-radius: var(--radius-sm) !important;
  border: 1px solid transparent;
  color: var(--text-muted);
}

.rail-nav-btn--idle {
  background: transparent;
}

.rail-nav-btn--idle:hover {
  border-color: var(--border-hover);
  background: var(--card-bg-hover);
  color: var(--text-primary);
  transform: translateY(-1px);
}

.rail-nav-btn--active {
  border-color: color-mix(in srgb, var(--rail-accent, var(--color-primary)) 28%, var(--border-subtle));
  background: color-mix(in srgb, var(--rail-accent, var(--color-primary)) 12%, var(--card-bg));
  color: var(--rail-accent, var(--color-primary));
  box-shadow: inset 3px 0 0 var(--rail-accent, var(--color-primary));
}

.rail-nav-btn__badge {
  height: 1.125rem;
  border: 1px solid var(--border-subtle);
  background: var(--color-primary);
  color: white;
}

.rail-tooltip {
  border-radius: var(--radius-sm) !important;
  border: 1px solid var(--border-subtle);
  background: var(--space-panel);
  min-width: 7rem;
}
</style>
