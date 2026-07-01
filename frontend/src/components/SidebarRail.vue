<template>
  <aside class="z-50 hidden h-full w-[104px] shrink-0 px-4 py-5 lg:flex">
    <div
      class="rail-shell relative flex h-full w-full flex-col items-center overflow-visible px-2 py-4 transition-all duration-300"
      :class="drawerOpen ? 'rounded-l-2xl rounded-r-xl' : 'rounded-2xl'"
    >
      <div class="rail-shell__aura pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]" />

      <div class="rail-brand relative z-10 flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl">
        <span class="text-[15px] font-black tracking-[0.12em] text-text-primary">EA</span>
      </div>

      <div class="rail-divider relative z-10 my-4 h-px w-9" />

      <nav class="relative z-10 flex w-full flex-col items-center gap-3" aria-label="Workspace Sidebar">
        <button
          v-for="(item, index) in items"
          :key="item.key"
          type="button"
          class="focus-ring rail-nav-btn group relative flex h-[60px] w-[56px] shrink-0 items-center justify-center rounded-2xl transition-all duration-200"
          :class="item.key === activePanel ? 'rail-nav-btn--active' : 'rail-nav-btn--idle'"
          :aria-label="item.label"
          :aria-controls="panelId"
          :aria-expanded="String(drawerOpen && item.key === activePanel)"
          aria-haspopup="dialog"
          :aria-pressed="String(drawerOpen && item.key === activePanel)"
          :title="item.label"
          @click="$emit('select', item.key)"
        >
          <component :is="item.icon" :size="22" />

          <span
            v-if="item.badge"
            class="rail-nav-btn__badge absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-[10px] font-black leading-none"
          >
            {{ item.badge }}
          </span>

          <span class="rail-tooltip pointer-events-none absolute left-[calc(100%+14px)] top-1/2 z-50 flex -translate-y-1/2 items-center gap-3 whitespace-nowrap rounded-2xl px-3 py-2 text-left opacity-0 shadow-[0_18px_42px_rgba(15,23,42,0.14)] transition-all duration-200 group-hover:translate-x-1 group-hover:opacity-100 group-focus-visible:translate-x-1 group-focus-visible:opacity-100">
            <span class="flex h-8 w-8 items-center justify-center rounded-xl bg-primary-soft text-primary">
              <component :is="item.icon" :size="16" />
            </span>
            <span>
              <span class="block text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">{{ item.short }}</span>
              <span class="mt-0.5 block text-xs font-semibold text-text-primary">{{ item.label }}</span>
            </span>
          </span>
        </button>
      </nav>

      <div class="relative z-10 mt-auto flex w-[58px] shrink-0 flex-col items-center rounded-2xl border border-subtle bg-space-elevated px-2 py-3 text-center">
        <span class="text-[9px] font-black uppercase tracking-[0.16em] text-text-muted">PATH</span>
        <span class="mt-2 text-[28px] font-black leading-none text-text-primary">{{ pathCount }}</span>
        <span class="mt-2 h-2 w-2 rounded-full bg-success shadow-[0_0_12px_var(--color-success)]" aria-label="Ready" />
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed } from "vue";
import IconRadar from "./icons/IconRadar.vue";
import IconSettings from "./icons/IconSettings.vue";
import IconTree from "./icons/IconTree.vue";

const props = defineProps({
  activePanel: { type: String, default: "tree" },
  drawerOpen: { type: Boolean, default: false },
  panelId: { type: String, default: "workspace-sidebar-drawer" },
  pathCount: { type: Number, default: 0 },
});

defineEmits(["select"]);

const items = computed(() => [
  { key: "tree", short: "PATH", label: "知识路径", icon: IconTree, badge: props.pathCount || "" },
  { key: "radar", short: "RADAR", label: "能力诊断", icon: IconRadar, badge: "" },
  { key: "settings", short: "SYSTEM", label: "工作台设置", icon: IconSettings, badge: "" },
]);

</script>

<style scoped>
.rail-shell {
  border: 1px solid var(--border-subtle);
  background: var(--space-panel);
  box-shadow: var(--workspace-shadow-soft);
}

.rail-shell__aura {
  background: linear-gradient(180deg, var(--color-primary-soft), transparent 32%);
  opacity: 0.55;
}

.rail-brand {
  border: 1px solid color-mix(in srgb, var(--color-primary) 24%, var(--border-subtle));
  background: var(--color-primary-soft);
  box-shadow: none;
  color: var(--color-primary-dark);
}

.rail-divider {
  background: linear-gradient(90deg, transparent, var(--border-strong), transparent);
}

.rail-nav-btn {
  border: 1px solid transparent;
  color: var(--text-muted);
}

.rail-nav-btn--active {
  border-color: color-mix(in srgb, var(--color-primary) 34%, var(--border-subtle));
  background: var(--color-primary);
  color: var(--color-primary-text);
  box-shadow: 0 8px 16px rgba(15, 118, 110, 0.18);
}

.rail-nav-btn--idle {
  background: var(--space-elevated);
  box-shadow: none;
}

.rail-nav-btn--idle:hover {
  border-color: color-mix(in srgb, var(--color-primary) 24%, var(--border-subtle));
  color: var(--text-primary);
  transform: translateY(-1px);
}

.rail-nav-btn__badge {
  border: 1px solid var(--border-subtle);
  background: var(--space-panel);
  color: var(--text-primary);
  box-shadow: var(--workspace-shadow-soft);
}

.rail-tooltip {
  border: 1px solid var(--border-subtle);
  background: var(--space-panel);
}
</style>
