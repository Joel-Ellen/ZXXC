<template>
  <article
    class="relative w-full rounded-[22px] p-6 backdrop-blur-sm transition-all duration-300"
    :class="[
      !isReady
        ? 'border border-subtle bg-card opacity-70'
        : `${colorClasses.border} ${colorClasses.hoverBorder} bg-card hover:shadow-card hover:-translate-y-0.5`,
      isActive ? 'shadow-[0_12px_36px_rgba(0,0,0,0.32)]' : '',
    ]"
  >
    <div class="mb-5 flex items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <span
          class="h-2.5 w-2.5 rounded-full"
          :class="isReady ? colorClasses.dot : 'bg-tertiary animate-pulse'"
          :style="isReady ? colorClasses.dotStyle : {}"
        />
        <div class="min-w-0">
          <h5 class="truncate font-mono text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">
            {{ agentName }}
          </h5>
          <p class="mt-0.5 truncate text-[11px] font-light uppercase tracking-[0.12em] text-text-muted/70">
            {{ title }}
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <div v-if="!isReady" class="text-right font-mono text-[10px] tracking-[0.14em] text-text-muted">
          <div>{{ progressText }}</div>
          <div>{{ progress }}%</div>
        </div>
        <span v-else class="font-mono text-[10px] tracking-[0.16em] text-text-muted">
          已验证
        </span>
        <button
          type="button"
          class="focus-ring rounded-full border border-subtle p-2 text-text-muted transition-all duration-200 hover:border-primary/30 hover:text-primary hover:bg-card-hover active:scale-95"
          aria-label="置顶卡片"
          @click="$emit('pin')"
        >
          <IconPin />
        </button>
        <button
          type="button"
          class="focus-ring rounded-full border border-subtle p-2 text-text-muted transition-all duration-200 hover:border-secondary/30 hover:text-secondary hover:bg-card-hover active:scale-95"
          aria-label="最小化卡片"
          @click="$emit('minimize')"
        >
          <IconMinimize />
        </button>
      </div>
    </div>

    <div class="relative min-h-[100px]">
      <div v-if="!isReady" class="absolute inset-0 space-y-3 overflow-hidden rounded-2xl">
        <div
          v-for="width in ['w-full', 'w-5/6', 'w-2/3']"
          :key="width"
          class="h-4 overflow-hidden rounded-lg bg-card"
          :class="width"
        >
          <div class="h-full w-1/2 bg-gradient-to-r from-transparent via-[var(--text-muted)]/10 to-transparent animate-shimmer" />
        </div>
        <div class="mt-4 h-px w-full bg-[var(--border-strong)]">
          <div
            class="h-px bg-gradient-to-r from-primary to-secondary transition-all duration-500"
            :style="{ width: `${progress}%` }"
          />
        </div>
      </div>

      <div
        class="text-sm font-normal leading-relaxed tracking-wide text-text-secondary"
        :class="{
          'pointer-events-none opacity-0': !isReady,
          'opacity-100 transition-opacity duration-500': isReady,
        }"
      >
        <slot name="content" />
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed } from "vue";
import IconMinimize from "./icons/IconMinimize.vue";
import IconPin from "./icons/IconPin.vue";

const props = defineProps({
  agentName: { type: String, default: "" },
  title: { type: String, default: "" },
  progressText: { type: String, default: "网格同步" },
  progress: { type: Number, default: 0 },
  isReady: { type: Boolean, default: false },
  isActive: { type: Boolean, default: false },
  color: { type: String, default: "primary" },
});

defineEmits(["pin", "minimize"]);

const COLOR_MAP = {
  primary: {
    border: "border-primary-soft",
    hoverBorder: "hover:border-primary/30",
    dot: "bg-primary",
    cssVar: "var(--color-primary)",
  },
  secondary: {
    border: "border-secondary-soft",
    hoverBorder: "hover:border-secondary/30",
    dot: "bg-secondary",
    cssVar: "var(--color-secondary)",
  },
  tertiary: {
    border: "border-tertiary-soft",
    hoverBorder: "hover:border-tertiary/30",
    dot: "bg-tertiary",
    cssVar: "var(--color-tertiary)",
  },
  success: {
    border: "border-success-soft",
    hoverBorder: "hover:border-success/30",
    dot: "bg-success",
    cssVar: "var(--color-success)",
  },
  warning: {
    border: "border-warning-soft",
    hoverBorder: "hover:border-warning/30",
    dot: "bg-warning",
    cssVar: "var(--color-warning)",
  },
  error: {
    border: "border-error-soft",
    hoverBorder: "hover:border-error/30",
    dot: "bg-error",
    cssVar: "var(--color-error)",
  },
  info: {
    border: "border-info-soft",
    hoverBorder: "hover:border-info/30",
    dot: "bg-info",
    cssVar: "var(--color-info)",
  },
};

const colorClasses = computed(() => {
  const config = COLOR_MAP[props.color] || COLOR_MAP.primary;
  return {
    border: config.border,
    hoverBorder: config.hoverBorder,
    dot: config.dot,
    dotStyle: { boxShadow: `0 0 12px ${config.cssVar}` },
  };
});
</script>
