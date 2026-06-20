<template>
  <aside class="hidden h-full w-[76px] flex-col items-center justify-start py-4 pl-3 pr-2 lg:flex z-50">
    <div
      class="relative flex h-full w-full flex-col items-center gap-2 border border-subtle bg-space-panel px-2 py-4 shadow-glass backdrop-blur-xl overflow-hidden transition-all duration-300"
      :class="drawerOpen ? 'rounded-l-[24px] rounded-r-none' : 'rounded-[24px]'"
    >
      <!-- Active indicator pill -->
      <div
        class="absolute left-1.5 w-1 rounded-full bg-primary shadow-glow transition-all duration-300 ease-snap"
        :style="{ top: `${indicatorTop}px`, height: '28px', opacity: activeIndex >= 0 ? 1 : 0 }"
      />

      <button
        v-for="(item, index) in items"
        :key="item.key"
        :ref="(el) => setButtonRef(el, index)"
        type="button"
        class="focus-ring group relative flex h-14 w-14 items-center justify-center rounded-[16px] text-text-muted transition-all duration-300"
        :class="item.key === activePanel
          ? 'bg-gradient-to-br from-primary to-primary-dark text-primary-text shadow-glow-primary'
          : 'hover:bg-card-hover hover:text-text-secondary active:scale-[0.95]'"
        :aria-label="item.label"
        :aria-pressed="item.key === activePanel"
        @click="$emit('select', item.key)"
      >
        <component :is="item.icon" :size="22" />

        <!-- Hover tooltip -->
        <span
          v-if="!drawerOpen || item.key !== activePanel"
          class="pointer-events-none absolute left-full ml-2 rounded-lg border border-subtle bg-space-panel px-2.5 py-1 text-[11px] font-medium text-text-secondary opacity-0 shadow-lg backdrop-blur-md transition-all duration-200 group-hover:opacity-100 whitespace-nowrap z-50"
        >
          {{ item.label }}
        </span>

        <span
          v-if="item.badge"
          class="absolute -right-1 -top-1 min-w-5 rounded-full border border-black/20 bg-tertiary px-1.5 py-0.5 text-[10px] font-semibold text-tertiary-text shadow-glow-tertiary"
        >
          {{ item.badge }}
        </span>
      </button>

      <div class="mt-2 h-full w-px bg-gradient-to-b from-[var(--border-strong)] via-[var(--border-subtle)] to-transparent" />
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch, nextTick } from "vue";
import IconRadar from "./icons/IconRadar.vue";
import IconSettings from "./icons/IconSettings.vue";
import IconTree from "./icons/IconTree.vue";

const props = defineProps({
  activePanel: { type: String, default: "tree" },
  drawerOpen: { type: Boolean, default: false },
  pathCount: { type: Number, default: 0 },
});

defineEmits(["select"]);

const buttonRefs = ref([]);
const indicatorTop = ref(16);

function setButtonRef(el, index) {
  if (el) {
    buttonRefs.value[index] = el;
  }
}

const items = computed(() => [
  { key: "tree", label: "知识路径", icon: IconTree, badge: props.pathCount || "" },
  { key: "radar", label: "能力雷达", icon: IconRadar, badge: "" },
  { key: "settings", label: "工作台设置", icon: IconSettings, badge: "" },
]);

const activeIndex = computed(() =>
  items.value.findIndex((item) => item.key === props.activePanel),
);

watch(
  () => props.activePanel,
  async () => {
    await nextTick();
    const activeBtn = buttonRefs.value[activeIndex.value];
    if (activeBtn) {
      indicatorTop.value = activeBtn.offsetTop + (activeBtn.offsetHeight - 28) / 2;
    }
  },
  { immediate: true },
);
</script>
