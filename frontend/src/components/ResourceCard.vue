<template>
  <article
    class="relative w-full overflow-hidden rounded-[20px] p-6 backdrop-blur-sm transition-all duration-300"
    :class="[
      !isReady
        ? 'border border-subtle bg-card opacity-80'
        : `${colorClasses.border} ${colorClasses.hoverBorder} bg-card hover:-translate-y-0.5 hover:shadow-card`,
      isActive ? 'shadow-[var(--workspace-shadow-focus)] ring-1 ring-white/10' : '',
      activatable ? 'cursor-pointer' : '',
    ]"
    :aria-label="activationLabel"
    :aria-current="isActive ? 'true' : undefined"
    :aria-expanded="activatable ? String(isExpanded) : undefined"
    :aria-keyshortcuts="activatable ? 'Enter Space' : undefined"
    :aria-pressed="activatable ? String(isActive) : undefined"
    :role="activatable ? 'button' : undefined"
    :tabindex="activatable ? 0 : undefined"
    @click="handleActivate"
    @keydown.enter.self.prevent="handleActivate"
    @keydown.space.self.prevent="handleActivate"
  >
    <div class="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/12 to-transparent" />
    <div
      v-if="isActive"
      class="pointer-events-none absolute inset-x-6 top-0 h-20 rounded-b-[28px] opacity-80 blur-2xl"
      :style="{ background: `linear-gradient(180deg, ${colorClasses.glow}, transparent)` }"
    />

    <div class="mb-5 flex items-start justify-between gap-3">
      <div class="flex min-w-0 items-center gap-3">
        <span
          class="mt-1 h-2.5 w-2.5 rounded-full"
          :class="isReady ? colorClasses.dot : 'bg-tertiary animate-pulse'"
          :style="isReady ? colorClasses.dotStyle : {}"
        />
        <div class="min-w-0">
          <h5 class="truncate font-mono text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">
            {{ agentName }}
          </h5>
          <p class="mt-0.5 truncate text-[13px] font-semibold tracking-[0.02em] text-text-primary">
            {{ displayTitle }}
          </p>
        </div>
      </div>

      <div class="flex shrink-0 items-start gap-2">
        <div class="rounded-full border border-subtle bg-space-surface/60 px-2.5 py-1 text-right">
          <div class="font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted">
            {{ isReady ? "已就绪" : progressText }}
          </div>
          <div v-if="!isReady && hasProgress" class="mt-1 text-[11px] font-semibold text-text-secondary">
            {{ progress }}%
          </div>
          <div v-else-if="!isReady" class="mt-1 flex items-center justify-end gap-1.5 text-[11px] font-semibold text-text-secondary" aria-live="polite">
            <span class="h-1.5 w-1.5 rounded-full bg-tertiary animate-pulse" aria-hidden="true" />
            <span>处理中</span>
          </div>
        </div>

        <button
          v-if="showPin"
          type="button"
          class="focus-ring rounded-full border border-subtle p-2 text-text-muted transition-all duration-200 hover:border-primary/30 hover:bg-card-hover hover:text-primary active:scale-95"
          aria-label="置顶卡片"
          @click.stop="$emit('pin')"
        >
          <IconPin />
        </button>
        <button
          type="button"
          class="focus-ring inline-flex h-11 min-h-11 w-11 min-w-11 shrink-0 items-center justify-center rounded-full border border-subtle p-0 transition-all duration-200 hover:border-warning/30 hover:bg-card-hover hover:text-warning active:scale-95"
          :class="isBookmarked ? 'border-warning/35 bg-warning-soft text-warning' : 'text-text-muted'"
          :aria-label="isBookmarked ? '取消收藏资源' : '收藏资源'"
          :aria-pressed="String(isBookmarked)"
          :title="isBookmarked ? '取消收藏资源' : '收藏资源'"
          @click.stop="$emit('bookmark')"
        >
          <IconBookmark :filled="isBookmarked" />
        </button>
        <button
          v-if="showMinimize"
          type="button"
          class="focus-ring rounded-full border border-subtle p-2 text-text-muted transition-all duration-200 hover:border-secondary/30 hover:bg-card-hover hover:text-secondary active:scale-95"
          aria-label="最小化卡片"
          @click.stop="$emit('minimize')"
        >
          <IconMinimize />
        </button>
      </div>
    </div>

    <div class="mb-5 h-px w-full bg-gradient-to-r from-transparent via-[var(--border-strong)] to-transparent" />

    <div class="relative min-h-[120px]">
      <div v-if="!isReady" class="absolute inset-0 space-y-3 overflow-hidden rounded-2xl">
        <div
          v-for="width in ['w-full', 'w-5/6', 'w-2/3']"
          :key="width"
          class="h-4 overflow-hidden rounded-lg bg-card"
          :class="width"
        >
          <div class="h-full w-1/2 animate-shimmer bg-gradient-to-r from-transparent via-[var(--text-muted)]/10 to-transparent" />
        </div>
        <div v-if="hasProgress" class="mt-4 rounded-full bg-[var(--border-strong)]/80 p-[1px]">
          <div
            class="h-1.5 rounded-full bg-gradient-to-r from-primary to-secondary transition-all duration-500"
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

    <div class="mt-6 flex flex-wrap items-center justify-between gap-2">
      <p class="text-[11px] text-text-muted">{{ footerLabel }}</p>
      <div class="flex items-center gap-2 text-[11px] text-text-muted">
        <span class="rounded-full border border-subtle bg-space-surface/50 px-2.5 py-1">
          {{ isExpanded ? "内容已展开" : isActive ? "当前卡片" : "可设为当前" }}
        </span>
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed } from "vue";
import IconBookmark from "./icons/IconBookmark.vue";
import IconMinimize from "./icons/IconMinimize.vue";
import IconPin from "./icons/IconPin.vue";

const props = defineProps({
  agentName: { type: String, default: "" },
  title: { type: String, default: "" },
  resource: { type: Object, default: null },
  progressText: { type: String, default: "栅格同步" },
  progress: { type: Number, default: null },
  isReady: { type: Boolean, default: false },
  isActive: { type: Boolean, default: false },
  isExpanded: { type: Boolean, default: false },
  isBookmarked: { type: Boolean, default: false },
  activatable: { type: Boolean, default: false },
  showPin: { type: Boolean, default: true },
  showMinimize: { type: Boolean, default: true },
  color: { type: String, default: "primary" },
});

const displayTitle = computed(() => (
  props.resource?.title
  || props.resource?.structured_payload?.title
  || props.resource?.metadata?.title
  || props.title
));
const hasProgress = computed(() => Number.isFinite(props.progress));
const emit = defineEmits(["activate", "pin", "bookmark", "minimize"]);

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
    glow: `color-mix(in srgb, ${config.cssVar} 18%, transparent)`,
  };
});

const activationLabel = computed(() => {
  if (props.isExpanded) {
    return "当前卡片内容已展开";
  }

  if (props.isActive) {
    return "展开当前卡片内容";
  }

  return "设为当前卡片并展开内容";
});

const footerLabel = computed(() => (
  props.isReady
    ? "支持置顶、切换与最小化，便于按你的学习顺序重排内容。"
    : "资源仍在装配中，建议暂时停留在当前节点等待生成完成。"
));
function handleActivate() {
  if (!props.activatable) {
    return;
  }

  emit("activate");
}
</script>
