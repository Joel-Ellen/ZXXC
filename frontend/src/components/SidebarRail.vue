<template>
  <aside class="hidden h-full w-16 flex-col items-center justify-start py-4 lg:flex">
    <div class="flex h-full w-full flex-col items-center gap-3 rounded-[28px] border border-white/[0.03] bg-[linear-gradient(180deg,rgba(255,255,255,0.02),rgba(255,255,255,0.008))] px-2 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.02),inset_0_-18px_32px_rgba(0,0,0,0.42)] backdrop-blur-md">
      <button
        v-for="item in items"
        :key="item.key"
        type="button"
        class="focus-ring group relative flex h-11 w-11 items-center justify-center rounded-[16px] text-[#69708A] transition duration-300"
        :class="item.key === activePanel
          ? 'border border-white/[0.06] bg-[linear-gradient(180deg,rgba(0,242,254,0.12),rgba(255,255,255,0.02))] text-[#EAF1FB] shadow-[0_0_0_1px_rgba(0,242,254,0.08),0_10px_28px_rgba(0,0,0,0.26)]'
          : 'border border-transparent bg-transparent hover:border-white/[0.04] hover:bg-white/[0.015] hover:text-[#EEF2FB]'"
        :aria-label="item.label"
        @click="$emit('select', item.key)"
      >
        <component :is="item.icon" />
        <span
          v-if="item.badge"
          class="absolute -right-1 -top-1 min-w-5 rounded-full border border-black/20 bg-aurora-crimson px-1.5 py-0.5 text-[10px] font-semibold text-white shadow-[0_0_12px_rgba(255,51,102,0.45)]"
        >
          {{ item.badge }}
        </span>
      </button>

      <div class="mt-1 h-full w-px bg-gradient-to-b from-white/[0.08] via-white/[0.02] to-transparent" />
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
  pathCount: { type: Number, default: 0 },
});

defineEmits(["select"]);

const items = computed(() => [
  { key: "tree", label: "Knowledge Path", icon: IconTree, badge: props.pathCount || "" },
  { key: "radar", label: "Capability Radar", icon: IconRadar, badge: "" },
  { key: "settings", label: "Workbench Settings", icon: IconSettings, badge: "" },
]);
</script>
