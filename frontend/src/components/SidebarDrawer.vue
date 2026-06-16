<template>
  <transition name="drawer">
    <aside
      v-if="open"
      class="fixed bottom-4 left-4 right-4 top-24 z-30 flex overflow-hidden rounded-[30px] border border-white/[0.035] bg-[linear-gradient(180deg,rgba(13,14,21,0.94),rgba(10,11,18,0.92))] shadow-[0_28px_60px_rgba(0,0,0,0.38),inset_0_1px_0_rgba(255,255,255,0.02),inset_0_-28px_42px_rgba(0,0,0,0.42)] backdrop-blur-[18px] lg:inset-y-4 lg:left-24 lg:right-auto lg:top-4 lg:w-[300px]"
    >
      <div class="flex w-full flex-col">
        <div class="relative px-6 pb-5 pt-5">
          <div class="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-white/[0.08] to-transparent" />
          <p class="text-[10px] font-black uppercase tracking-[0.16em] text-[#4A4F68]">Mesh Console</p>
          <h2 class="mt-2 text-[28px] font-black uppercase tracking-[-0.05em] text-[#F0F3FB]">{{ panelTitle }}</h2>
          <p class="mt-2 max-w-[22ch] text-xs font-light leading-6 text-[#4A4F68]">
            {{ panelDescription }}
          </p>
        </div>

        <div class="aurora-scroll flex-1 overflow-y-auto px-5 pb-5">
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
          <div v-else class="space-y-4">
            <section class="rounded-[20px] border border-white/[0.035] bg-white/[0.02] p-4 shadow-[inset_0_1px_8px_rgba(0,0,0,0.34)]">
              <h3 class="text-[11px] font-black uppercase tracking-[0.14em] text-[#E9EDF8]">High Contrast</h3>
              <p class="mt-2 text-xs font-light leading-6 text-[#4A4F68]">
                Increase mint and iris contrast for long-form reading and denser node scanning.
              </p>
              <button
                type="button"
                class="focus-ring mt-4 rounded-full border border-white/[0.05] px-3 py-2 text-[11px] font-black uppercase tracking-[0.14em] text-[#8A90A8] transition hover:border-aurora-mint/25 hover:text-[#EEF2FB]"
                @click="$emit('toggle-contrast')"
              >
                {{ highContrast ? "Enabled" : "Enable" }}
              </button>
            </section>

            <section class="rounded-[20px] border border-white/[0.035] bg-white/[0.02] p-4 shadow-[inset_0_1px_8px_rgba(0,0,0,0.34)]">
              <h3 class="text-[11px] font-black uppercase tracking-[0.14em] text-[#E9EDF8]">Base Font Size</h3>
              <p class="mt-2 text-xs font-light leading-6 text-[#4A4F68]">
                Adjust the workbench typography between 14 and 20 pixels.
              </p>
              <input
                class="mt-4 w-full accent-[#00F2FE]"
                type="range"
                min="14"
                max="20"
                :value="fontSize"
                @input="$emit('set-font-size', Number($event.target.value))"
              />
              <p class="mt-2 text-[11px] font-mono uppercase tracking-[0.14em] text-[#6E748B]">{{ fontSize }}px</p>
            </section>

            <section class="rounded-[20px] border border-white/[0.035] bg-white/[0.02] p-4 shadow-[inset_0_1px_8px_rgba(0,0,0,0.34)]">
              <h3 class="text-[11px] font-black uppercase tracking-[0.14em] text-[#E9EDF8]">Reduced Motion</h3>
              <p class="mt-2 text-xs font-light leading-6 text-[#4A4F68]">
                Respect system preference and allow manual damping of motion across the interface.
              </p>
              <button
                type="button"
                class="focus-ring mt-4 rounded-full border border-white/[0.05] px-3 py-2 text-[11px] font-black uppercase tracking-[0.14em] text-[#8A90A8] transition hover:border-aurora-purple/25 hover:text-[#EEF2FB]"
                @click="$emit('toggle-motion')"
              >
                {{ reduceMotion ? "Enabled" : "Enable" }}
              </button>
            </section>
          </div>
        </div>
      </div>
    </aside>
  </transition>
</template>

<script setup>
import { computed } from "vue";
import KnowledgeTree from "./KnowledgeTree.vue";
import RadarCanvas from "./RadarCanvas.vue";

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
]);

const titles = {
  tree: "Knowledge Tree",
  radar: "Capability Radar",
  settings: "Workbench Settings",
};

const descriptions = {
  tree: "Trace the learning topology, inspect mastery states, and jump directly into the next node.",
  radar: "Review capability balance across concept comprehension, engineering, and timing discipline.",
  settings: "Tune visual contrast, typography, and motion behavior for the current workbench session.",
};

const panelTitle = computed(() => titles[props.activePanel] ?? "Workbench");
const panelDescription = computed(() => descriptions[props.activePanel] ?? "Workbench controls.");
</script>
