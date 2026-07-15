<template>
  <div
    class="workspace-shell relative z-10 flex overflow-hidden font-sans text-text-primary animate-fadeIn"
    :class="{
      'is-high-contrast': highContrast,
      'is-reduced-motion': reduceMotion,
    }"
    :aria-busy="busy ? 'true' : 'false'"
    :style="fontScaleStyle"
    @wheel="$emit('workspace-wheel', $event)"
  >
    <SidebarRail
      v-if="showRail"
      :active-panel="activePanel"
      :drawer-open="drawerOpen"
      :panel-id="panelId"
      :path-count="pathNodes.length"
      @select="$emit('select-panel', $event)"
    />

    <div class="workspace-shell__body relative flex min-w-0 flex-1 flex-col">
      <slot name="header" />

      <div class="workspace-shell__main relative flex min-h-0 flex-1 flex-col">
        <slot />
      </div>

      <slot name="floating" />
      <slot name="drawer" />
      <slot name="overlay" />
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import SidebarRail from "../SidebarRail.vue";

const props = defineProps({
  pathNodes: { type: Array, default: () => [] },
  activePanel: { type: String, default: "concept" },
  drawerOpen: { type: Boolean, default: false },
  panelId: { type: String, default: "workspace-sidebar-drawer" },
  highContrast: { type: Boolean, default: false },
  reduceMotion: { type: Boolean, default: false },
  fontSize: { type: Number, default: 16 },
  busy: { type: Boolean, default: false },
  showRail: { type: Boolean, default: true },
});

defineEmits(["select-panel", "workspace-wheel"]);

const FONT_STEPS = [8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 28, 30];

const fontScaleStyle = computed(() => {
  const baseSize = Math.max(14, Math.min(20, Number(props.fontSize) || 16));
  const scale = baseSize / 16;
  const styles = {
    fontSize: `${baseSize}px`,
    "--font-size-xs": scaledFontSize(12, scale),
    "--font-size-sm": scaledFontSize(14, scale),
    "--font-size-md": scaledFontSize(16, scale),
    "--font-size-lg": scaledFontSize(18, scale),
    "--font-size-xl": scaledFontSize(20, scale),
  };

  FONT_STEPS.forEach((size) => {
    styles[`--workspace-font-${size}`] = scaledFontSize(size, scale);
  });

  return styles;
});

function scaledFontSize(size, scale) {
  return `${Number((size * scale).toFixed(2))}px`;
}
</script>

<style scoped>
.workspace-shell {
  width: 100%;
  height: 100dvh;
  min-height: 100dvh;
  min-height: 0;
  padding-top: env(safe-area-inset-top, 0px);
  padding-right: env(safe-area-inset-right, 0px);
  padding-left: env(safe-area-inset-left, 0px);
}

.workspace-shell.is-high-contrast {
  filter: contrast(1.06) saturate(1.03);
}

.workspace-shell.is-reduced-motion,
.workspace-shell.is-reduced-motion * {
  animation-duration: var(--duration-instant) !important;
  animation-iteration-count: 1 !important;
  scroll-behavior: auto !important;
  transition-duration: var(--duration-instant) !important;
}

.workspace-shell__body {
  width: 100%;
  background: var(--space-bg);
}

.workspace-shell__main {
  width: 100%;
  isolation: isolate;
}

@media (max-width: 767px) {
  .workspace-shell__body,
  .workspace-shell__main {
    max-width: 100vw;
    overflow-x: hidden;
  }
}

.workspace-shell :deep(.text-xs),
.workspace-shell :deep([class~="text-[12px]"]) {
  font-size: var(--workspace-font-12);
}

.workspace-shell :deep(.text-sm) {
  font-size: var(--workspace-font-14);
}

.workspace-shell :deep(.text-base) {
  font-size: var(--workspace-font-16);
}

.workspace-shell :deep(.text-lg),
.workspace-shell :deep([class~="text-[18px]"]) {
  font-size: var(--workspace-font-18);
}

.workspace-shell :deep(.text-xl) {
  font-size: var(--workspace-font-20);
}

.workspace-shell :deep(.text-2xl) {
  font-size: var(--workspace-font-24);
}

.workspace-shell :deep(.text-3xl),
.workspace-shell :deep([class~="text-[30px]"]) {
  font-size: var(--workspace-font-30);
}

.workspace-shell :deep([class~="text-[8px]"]) {
  font-size: var(--workspace-font-8);
}

.workspace-shell :deep([class~="text-[9px]"]) {
  font-size: var(--workspace-font-9);
}

.workspace-shell :deep([class~="text-[10px]"]) {
  font-size: var(--workspace-font-10);
}

.workspace-shell :deep([class~="text-[11px]"]) {
  font-size: var(--workspace-font-11);
}

.workspace-shell :deep([class~="text-[13px]"]) {
  font-size: var(--workspace-font-13);
}

.workspace-shell :deep([class~="text-[15px]"]) {
  font-size: var(--workspace-font-15);
}

.workspace-shell :deep([class~="text-[22px]"]) {
  font-size: var(--workspace-font-22);
}

.workspace-shell :deep([class~="text-[28px]"]) {
  font-size: var(--workspace-font-28);
}

.workspace-shell :deep(.resource-canvas__eyebrow),
.workspace-shell :deep(.resource-canvas__nodes-label),
.workspace-shell :deep(.resource-canvas__metric span),
.workspace-shell :deep(.course-switcher__menu-label) {
  font-size: var(--workspace-font-11);
}

.workspace-shell :deep(.resource-canvas__title-line h2) {
  font-size: var(--workspace-font-22);
}

.workspace-shell :deep(.resource-canvas__metric strong),
.workspace-shell :deep(.resource-canvas__guidance),
.workspace-shell :deep(.session-header__mark) {
  font-size: var(--workspace-font-13);
}

.workspace-shell :deep(.course-switcher__icon) {
  font-size: var(--workspace-font-16);
}

.workspace-shell :deep(.course-switcher__item-meta),
.workspace-shell :deep(.session-header__pill) {
  font-size: var(--workspace-font-11);
}

.workspace-shell :deep(.session-header__brand-copy span),
.workspace-shell :deep(.session-header__label),
.workspace-shell :deep(.session-header__nav-button),
.workspace-shell :deep(.session-header__utility) {
  font-size: var(--workspace-font-12);
}

.workspace-shell :deep(.session-header__subtle),
.workspace-shell :deep(.session-header__user),
.workspace-shell :deep(.session-header__notice) {
  font-size: var(--workspace-font-13);
}

@media (min-width: 640px) {
  .workspace-shell :deep([class~="sm:text-xl"]) {
    font-size: var(--workspace-font-20);
  }

  .workspace-shell :deep([class~="sm:text-2xl"]) {
    font-size: var(--workspace-font-24);
  }

  .workspace-shell :deep([class~="sm:text-3xl"]) {
    font-size: var(--workspace-font-30);
  }
}

@media (min-width: 768px) {
  .workspace-shell :deep([class~="md:text-3xl"]) {
    font-size: var(--workspace-font-30);
  }
}
</style>
