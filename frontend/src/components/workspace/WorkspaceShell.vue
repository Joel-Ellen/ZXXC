<template>
  <div
    class="workspace-shell relative z-10 flex h-screen overflow-hidden font-sans text-text-primary animate-fadeIn"
    :class="{
      'is-high-contrast': highContrast,
      'is-reduced-motion': reduceMotion,
    }"
    :aria-busy="busy ? 'true' : 'false'"
    :style="{ fontSize: `${fontSize}px` }"
    @wheel="$emit('workspace-wheel', $event)"
  >
    <SidebarRail
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
import SidebarRail from "../SidebarRail.vue";

defineProps({
  pathNodes: { type: Array, default: () => [] },
  activePanel: { type: String, default: "concept" },
  drawerOpen: { type: Boolean, default: false },
  panelId: { type: String, default: "workspace-sidebar-drawer" },
  highContrast: { type: Boolean, default: false },
  reduceMotion: { type: Boolean, default: false },
  fontSize: { type: Number, default: 16 },
  busy: { type: Boolean, default: false },
});

defineEmits(["select-panel", "workspace-wheel"]);
</script>

<style scoped>
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
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--space-panel) 82%, transparent), transparent 36%),
    transparent;
}

.workspace-shell__main {
  isolation: isolate;
}
</style>
