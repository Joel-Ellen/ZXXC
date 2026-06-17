<template>
  <transition name="drawer-backdrop">
    <div
      v-if="open"
      class="fixed inset-0 z-40 lg:z-30"
      aria-hidden="true"
      @click.self="$emit('close')"
    >
      <!-- Backdrop overlay -->
      <div
        class="absolute inset-0 bg-black/40 backdrop-blur-sm transition-opacity lg:bg-black/10 lg:backdrop-blur-none"
      />

      <!-- Drawer panel -->
      <transition name="drawer-panel">
        <aside
          class="absolute bottom-4 left-4 right-4 top-24 z-10 flex overflow-hidden rounded-[28px] border border-subtle bg-space-panel shadow-2xl backdrop-blur-xl lg:inset-y-4 lg:left-[68px] lg:right-auto lg:top-4 lg:w-[380px] lg:rounded-l-none lg:border-l-0"
        >
          <div class="flex w-full flex-col">
            <!-- Header -->
            <div class="relative flex items-start gap-4 px-6 pb-5 pt-6">
              <div class="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-[var(--border-strong)] to-transparent" />

              <!-- Panel icon -->
              <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-[16px] bg-gradient-to-br from-primary-soft to-secondary-soft text-primary shadow-card">
                <component :is="panelIcon" :size="22" />
              </div>

              <div class="min-w-0 flex-1">
                <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">网格控制台</p>
                <h2 class="gradient-text mt-1.5 text-[28px] font-black tracking-tight">{{ panelTitle }}</h2>
                <p class="mt-2 max-w-[32ch] text-sm font-light leading-7 text-text-muted">
                  {{ panelDescription }}
                </p>
              </div>
            </div>

            <!-- Content -->
            <div class="aurora-scroll flex-1 overflow-y-auto px-5 pb-6">
              <KnowledgeTree
                v-if="activePanel === 'tree'"
                :nodes="nodes"
                :current-node="currentNode"
                @select="$emit('select-node', $event)"
              />
              <RadarCanvas
                v-else-if="activePanel === 'radar'"
                :values="radarValues"
                :high-contrast="highContrast"
              />
              <div v-else class="space-y-5">
                <!-- Theme selector -->
                <section class="rounded-[22px] border border-subtle bg-card p-5 shadow-card">
                  <h3 class="text-sm font-bold tracking-wide text-text-secondary">配色主题</h3>
                  <p class="mt-2 text-sm font-light leading-7 text-text-muted">
                    在深色与浅色主题之间切换，颜色范围已扩展并提升辨识度。
                  </p>
                  <div class="mt-5 flex gap-2 p-1 rounded-xl bg-card border border-subtle">
                    <button
                      type="button"
                      class="focus-ring flex flex-1 items-center justify-center gap-2 rounded-lg py-2 text-xs font-semibold tracking-wide transition-all duration-200"
                      :class="theme === 'dark'
                        ? 'bg-card-hover text-text-primary shadow-lg shadow-black/20'
                        : 'text-text-muted hover:text-text-secondary'"
                      @click="setTheme('dark')"
                    >
                      <span class="h-3 w-3 rounded-full bg-[#05060A] border border-white/20" />
                      深色
                    </button>
                    <button
                      type="button"
                      class="focus-ring flex flex-1 items-center justify-center gap-2 rounded-lg py-2 text-xs font-semibold tracking-wide transition-all duration-200"
                      :class="theme === 'light'
                        ? 'bg-card-hover text-text-primary shadow-lg shadow-black/20'
                        : 'text-text-muted hover:text-text-secondary'"
                      @click="setTheme('light')"
                    >
                      <span class="h-3 w-3 rounded-full bg-[#FAFAF8] border border-black/10" />
                      浅色
                    </button>
                  </div>
                </section>

                <section class="rounded-[22px] border border-subtle bg-card p-5 shadow-card">
                  <h3 class="text-sm font-bold tracking-wide text-text-secondary">高对比度</h3>
                  <p class="mt-2 text-sm font-light leading-7 text-text-muted">
                    提升主题色对比度，便于长时间阅读与密集节点扫描。
                  </p>
                  <button
                    type="button"
                    class="focus-ring mt-5 rounded-full border border-subtle bg-card px-4 py-2 text-xs font-semibold tracking-wide text-text-secondary transition-all duration-200 hover:border-primary/40 hover:text-primary hover:bg-card-hover"
                    @click="$emit('toggle-contrast')"
                  >
                    {{ highContrast ? "已启用" : "启用" }}
                  </button>
                </section>

                <section class="rounded-[22px] border border-subtle bg-card p-5 shadow-card">
                  <h3 class="text-sm font-bold tracking-wide text-text-secondary">基础字号</h3>
                  <p class="mt-2 text-sm font-light leading-7 text-text-muted">
                    在工作台 14 至 20 像素之间调整字体大小。
                  </p>
                  <input
                    class="mt-5 w-full accent-primary h-1.5 bg-[var(--border-strong)] rounded-lg appearance-none cursor-pointer"
                    type="range"
                    min="14"
                    max="20"
                    :value="fontSize"
                    @input="$emit('set-font-size', Number($event.target.value))"
                  />
                  <p class="mt-2 text-xs font-mono uppercase tracking-[0.14em] text-text-muted">{{ fontSize }}px</p>
                </section>

                <section class="rounded-[22px] border border-subtle bg-card p-5 shadow-card">
                  <h3 class="text-sm font-bold tracking-wide text-text-secondary">减少动效</h3>
                  <p class="mt-2 text-sm font-light leading-7 text-text-muted">
                    尊重系统偏好，并可手动减弱界面中的运动效果。
                  </p>
                  <button
                    type="button"
                    class="focus-ring mt-5 rounded-full border border-subtle bg-card px-4 py-2 text-xs font-semibold tracking-wide text-text-secondary transition-all duration-200 hover:border-secondary/40 hover:text-secondary hover:bg-card-hover"
                    @click="$emit('toggle-motion')"
                  >
                    {{ reduceMotion ? "已启用" : "启用" }}
                  </button>
                </section>
              </div>
            </div>

            <!-- Close handle (mobile) -->
            <button
              type="button"
              class="focus-ring absolute right-4 top-4 rounded-full p-2 text-text-muted transition hover:bg-card-hover hover:text-text-primary lg:hidden"
              aria-label="关闭侧边栏"
              @click="$emit('close')"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 6 6 18" />
                <path d="M6 6l12 12" />
              </svg>
            </button>
          </div>
        </aside>
      </transition>
    </div>
  </transition>
</template>

<script setup>
import { computed } from "vue";
import KnowledgeTree from "./KnowledgeTree.vue";
import RadarCanvas from "./RadarCanvas.vue";
import IconRadar from "./icons/IconRadar.vue";
import IconSettings from "./icons/IconSettings.vue";
import IconTree from "./icons/IconTree.vue";
import { useTheme } from "../composables/useTheme.js";

const { theme, setTheme } = useTheme();

const props = defineProps({
  open: { type: Boolean, default: false },
  activePanel: { type: String, default: "tree" },
  nodes: { type: Array, default: () => [] },
  currentNode: { type: String, default: "" },
  radarValues: { type: Array, default: () => [] },
  highContrast: { type: Boolean, default: false },
  reduceMotion: { type: Boolean, default: false },
  fontSize: { type: Number, default: 16 },
});

defineEmits([
  "select-node",
  "toggle-contrast",
  "toggle-motion",
  "set-font-size",
  "close",
]);

const panelIcons = {
  tree: IconTree,
  radar: IconRadar,
  settings: IconSettings,
};

const titles = {
  tree: "知识树",
  radar: "能力雷达",
  settings: "工作台设置",
};

const descriptions = {
  tree: "追踪学习拓扑，查看掌握状态，并直接跳转到下一个节点。",
  radar: "回顾概念理解、代码工程、逻辑推理等五项能力的平衡分布。",
  settings: "为当前工作台会话调整主题、对比度、字体与动效。",
};

const panelIcon = computed(() => panelIcons[props.activePanel] ?? IconSettings);
const panelTitle = computed(() => titles[props.activePanel] ?? "工作台");
const panelDescription = computed(() => descriptions[props.activePanel] ?? "工作台控制。");
</script>

<style scoped>
.drawer-backdrop-enter-active,
.drawer-backdrop-leave-active {
  transition: opacity 280ms ease;
}

.drawer-backdrop-enter-from,
.drawer-backdrop-leave-to {
  opacity: 0;
}

.drawer-panel-enter-active,
.drawer-panel-leave-active {
  transition: transform 320ms cubic-bezier(0.16, 1, 0.3, 1), opacity 260ms ease;
}

.drawer-panel-enter-from,
.drawer-panel-leave-to {
  transform: translateX(-24px) scale(0.98);
  opacity: 0;
}

input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-primary);
  box-shadow: 0 0 12px var(--color-primary-soft);
  cursor: pointer;
}

input[type="range"]::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-primary);
  box-shadow: 0 0 12px var(--color-primary-soft);
  cursor: pointer;
  border: none;
}
</style>
