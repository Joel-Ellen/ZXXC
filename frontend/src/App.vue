<template>
  <div class="relative h-screen w-screen overflow-hidden bg-[#07080B] text-gray-200 antialiased selection:bg-aurora-purple/30">
    <div class="pointer-events-none absolute inset-0 overflow-hidden">
      <div class="absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(0,242,254,0.08),transparent_28%),radial-gradient(circle_at_78%_20%,rgba(127,0,255,0.12),transparent_32%),radial-gradient(circle_at_52%_88%,rgba(24,30,66,0.42),transparent_24%)]" />
      <div
        class="absolute inset-0 opacity-40"
        style="background-image: radial-gradient(#1F2335 1px, transparent 1px); background-size: 24px 24px;"
      />
    </div>

    <header class="absolute left-0 right-0 top-0 z-50 h-14 overflow-hidden bg-[#07080B]/40 backdrop-blur-[20px]">
      <div class="absolute inset-x-0 bottom-0 h-8 bg-gradient-to-b from-transparent to-black/25" />
      <div class="relative flex h-full items-center justify-between gap-6 px-6">
        <div class="flex min-w-0 items-center gap-6">
          <label class="min-w-[180px]">
            <span class="block text-[10px] font-black uppercase tracking-[0.16em] text-[#4A4F68]">Course</span>
            <select
              v-model="selectedCourse"
              class="focus-ring mt-1.5 w-full appearance-none border-0 bg-transparent p-0 text-sm font-light text-[#D6DAE8]"
            >
              <option>Data Structures Studio</option>
              <option>Algorithm Design Lab</option>
            </select>
          </label>

          <div class="hidden min-w-[210px] lg:block">
            <span class="block text-[10px] font-black uppercase tracking-[0.16em] text-[#4A4F68]">Global Progress</span>
            <div class="mt-2 flex items-center gap-3">
              <div class="h-px flex-1 overflow-hidden bg-white/[0.08]">
                <div
                  class="h-px bg-gradient-to-r from-[#00F2FE] via-[#00F2FE]/80 to-[#7F00FF]"
                  :style="{ width: `${overallProgress}%` }"
                />
              </div>
              <span class="text-xs font-medium text-[#E9EDF8]">{{ overallProgress }}%</span>
              <span class="text-xs font-light text-[#4A4F68]">{{ masteredCount }}/{{ currentPathNodes.length }}</span>
            </div>
          </div>
        </div>

        <div class="flex min-w-0 flex-1 items-center justify-end gap-4">
          <TopStatusBar class="max-w-[920px] flex-1" :statuses="agentStatuses" />
          <button
            type="button"
            class="focus-ring flex h-10 w-10 items-center justify-center rounded-full border border-white/[0.04] bg-white/[0.015] text-[#7A8096] transition hover:border-white/[0.08] hover:text-[#E9EDF8]"
            aria-label="Open settings"
            @click="openSettings"
          >
            <IconSettings />
          </button>
          <div class="flex h-10 w-10 items-center justify-center rounded-full bg-[radial-gradient(circle_at_30%_30%,rgba(0,242,254,0.28),transparent_35%),linear-gradient(145deg,rgba(8,17,32,0.9),rgba(44,15,77,0.9))] text-[11px] font-black uppercase tracking-[0.14em] text-white">
            EA
          </div>
        </div>
      </div>
    </header>

    <main class="flex h-full w-full overflow-hidden pt-14">
      <div class="flex h-full w-full gap-0 px-4 pb-4">
        <SidebarRail
          :active-panel="drawerPanel"
          :path-count="currentPathNodes.length"
          @select="toggleDrawer"
        />

        <SidebarDrawer
          :open="isDrawerOpen"
          :active-panel="drawerPanel"
          :nodes="currentPathNodes"
          :current-node="currentNode"
          :radar-values="capabilityRadar"
          :high-contrast="highContrast"
          :reduce-motion="reduceMotion"
          :font-size="fontSize"
          @select-node="handleNodeSelect"
          @toggle-contrast="highContrast = !highContrast"
          @toggle-motion="reduceMotion = !reduceMotion"
          @set-font-size="fontSize = $event"
        />

        <div class="grid min-h-0 flex-1 gap-0" :class="gridClass">
          <div v-show="!isCanvasExpanded || isMobile" class="min-h-0">
            <ChatArea
              :messages="messages"
              :boot-mode="bootMode"
              :probe="probe"
              :probe-collected="probeCollected"
              :probe-total="probeTotal"
              :is-submitting-probe="isSubmittingProbe"
              :busy="isBusy"
              @submit-probe="submitProbe"
              @send="handleTutorSend"
            />
          </div>

          <div class="min-h-0">
            <section class="relative h-full min-h-0">
              <div class="absolute inset-0 bg-[#07080B]" />
              <div
                class="pointer-events-none absolute inset-0 opacity-30"
                style="background-image: radial-gradient(rgba(255,255,255,0.05) 1px, transparent 1px); background-size: 20px 20px;"
              />

              <div class="relative flex h-full min-h-0 flex-col">
                <div class="flex items-start justify-between px-8 pb-3 pt-6">
                  <div>
                    <p class="text-[10px] font-black uppercase tracking-[0.16em] text-[#4A4F68]">Canvas Control</p>
                    <p class="mt-2 text-sm font-light text-[#8A90A8]">
                      {{ bootMode === "probe" ? "Complete the probe to start assembling the canvas." : currentNodeTitle }}
                    </p>
                  </div>
                  <button
                    type="button"
                    class="focus-ring inline-flex items-center gap-2 rounded-full border border-white/[0.05] bg-transparent px-3 py-2 text-[11px] font-medium uppercase tracking-[0.14em] text-[#8A90A8] transition hover:border-aurora-mint/30 hover:text-[#E9EDF8]"
                    @click="toggleCanvas"
                  >
                    <IconExpand :class="isCanvasExpanded ? 'rotate-180 transition-transform' : 'transition-transform'" />
                    <span>{{ isCanvasExpanded ? "Show Tray" : "Split Aurora" }}</span>
                  </button>
                </div>

                <div class="min-h-0 flex-1">
                  <ResourceCanvas
                    :cards="currentCards"
                    :current-node="currentNode"
                    :node-title="currentNodeTitle"
                    :path-nodes="currentPathNodes"
                    :loading="isLoadingNode"
                    :get-card-label="getCardLabel"
                    :get-agent-label="getAgentLabel"
                    :build-quiz="parseQuizFromContent"
                    @submit-quiz="submitQuiz"
                    @select-node="handleNodeSelect"
                  />
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </main>

    <transition name="floating">
      <button
        v-if="isCanvasExpanded && !isMobile"
        type="button"
        class="focus-ring fixed bottom-6 left-6 z-40 flex h-12 w-12 items-center justify-center rounded-full border border-aurora-purple/20 bg-[#12091C]/80 text-text-primary shadow-[0_16px_30px_rgba(0,0,0,0.45)] backdrop-blur-md transition hover:border-aurora-purple/40 hover:bg-[#1A0D28]"
        @click="toggleCanvas"
      >
        <IconChat />
        <span
          v-if="unreadCount"
          class="absolute -right-1 -top-1 flex min-h-4 min-w-4 items-center justify-center rounded-full bg-aurora-crimson px-1 text-[10px] font-semibold text-white"
        >
          {{ unreadCount }}
        </span>
      </button>
    </transition>

    <transition name="floating">
      <div
        v-if="infoMessage"
        class="pointer-events-none fixed right-6 top-20 z-50 rounded-full border border-white/[0.05] bg-[#0D0E15]/88 px-4 py-2 text-xs font-light text-[#8A90A8] shadow-[0_10px_30px_rgba(0,0,0,0.35)] backdrop-blur-md"
      >
        {{ infoMessage }}
      </div>
    </transition>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import ChatArea from "./components/ChatArea.vue";
import ResourceCanvas from "./components/ResourceCanvas.vue";
import SidebarDrawer from "./components/SidebarDrawer.vue";
import SidebarRail from "./components/SidebarRail.vue";
import TopStatusBar from "./components/TopStatusBar.vue";
import IconChat from "./components/icons/IconChat.vue";
import IconExpand from "./components/icons/IconExpand.vue";
import IconSettings from "./components/icons/IconSettings.vue";
import { useEduAgent } from "./composables/useEduAgent";

const {
  bootMode,
  isBusy,
  isSubmittingProbe,
  isLoadingNode,
  currentNode,
  capabilityRadar,
  probe,
  probeCollected,
  probeTotal,
  currentCards,
  currentNodeTitle,
  currentPathNodes,
  messages,
  assistantDeliveryCount,
  agentStatuses,
  overallProgress,
  masteredCount,
  infoMessage,
  bootstrap,
  submitProbe,
  loadNode,
  submitQuiz,
  sendTutorMessage,
  getCardLabel,
  getAgentLabel,
  parseQuizFromContent,
} = useEduAgent();

const drawerPanel = ref("tree");
const isDrawerOpen = ref(false);
const isCanvasExpanded = ref(false);
const unreadCount = ref(0);
const fontSize = ref(16);
const highContrast = ref(false);
const reduceMotion = ref(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
const selectedCourse = ref("Data Structures Studio");
const isMobile = ref(window.innerWidth < 1024);

const gridClass = computed(() => {
  if (isMobile.value) {
    return "grid-cols-1";
  }
  return isCanvasExpanded.value ? "grid-cols-[0_minmax(0,1fr)]" : "grid-cols-[380px_minmax(0,1fr)]";
});

function syncBodyPreferences() {
  document.documentElement.style.setProperty("--base-font-size", `${fontSize.value}px`);
  document.body.classList.toggle("high-contrast", highContrast.value);
  document.body.classList.toggle("reduce-motion", reduceMotion.value);
}

function handleResize() {
  isMobile.value = window.innerWidth < 1024;
  if (isMobile.value) {
    isCanvasExpanded.value = false;
  }
}

function handlePointerMove(event) {
  if (window.innerWidth < 1024) {
    return;
  }
  const x = (event.clientX / window.innerWidth - 0.5) * 8;
  const y = (event.clientY / window.innerHeight - 0.5) * 8;
  document.body.style.setProperty("--grid-offset-x", `${x}px`);
  document.body.style.setProperty("--grid-offset-y", `${y}px`);
}

function toggleDrawer(panel) {
  if (drawerPanel.value === panel) {
    isDrawerOpen.value = !isDrawerOpen.value;
  } else {
    drawerPanel.value = panel;
    isDrawerOpen.value = true;
  }
}

function openSettings() {
  drawerPanel.value = "settings";
  isDrawerOpen.value = true;
}

async function handleNodeSelect(nodeId) {
  await loadNode(nodeId);
  if (isMobile.value) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

async function handleTutorSend(query) {
  isBusy.value = true;
  await sendTutorMessage(query);
  isBusy.value = false;
}

function toggleCanvas() {
  isCanvasExpanded.value = !isCanvasExpanded.value;
  if (!isCanvasExpanded.value) {
    unreadCount.value = 0;
  }
}

watch([fontSize, highContrast, reduceMotion], syncBodyPreferences, { immediate: true });

watch(
  () => assistantDeliveryCount.value,
  () => {
    if (isCanvasExpanded.value && !isMobile.value) {
      unreadCount.value += 1;
    }
  },
);

watch(
  () => isCanvasExpanded.value,
  (expanded) => {
    if (!expanded) {
      unreadCount.value = 0;
    }
  },
);

onMounted(async () => {
  syncBodyPreferences();
  window.addEventListener("resize", handleResize);
  window.addEventListener("pointermove", handlePointerMove);
  await bootstrap();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  window.removeEventListener("pointermove", handlePointerMove);
});
</script>
