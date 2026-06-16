<template>
  <article
    class="relative mb-6 w-full rounded-[18px] p-7 backdrop-blur-sm transition-all duration-500"
    :class="[
      !isReady
        ? 'border border-white/[0.03] bg-gradient-to-b from-white/[0.02] to-transparent opacity-70'
        : 'border border-white/[0.04] bg-gradient-to-b from-white/[0.02] to-transparent hover:border-aurora-mint/30 hover:shadow-[0_8px_32px_rgba(0,242,254,0.03)]',
      isActive ? 'shadow-[0_12px_36px_rgba(0,0,0,0.28)]' : '',
    ]"
  >
    <div class="mb-5 flex items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-2.5">
        <span
          class="h-1.5 w-1.5 rounded-full shadow-[0_0_8px_#00F2FE]"
          :class="isReady ? readyClass : 'bg-aurora-purple animate-pulse shadow-[0_0_8px_#7F00FF]'"
        />
        <div class="min-w-0">
          <h5 class="truncate font-mono text-[11px] font-black uppercase tracking-[0.15em] text-gray-400">
            {{ agentName }}
          </h5>
          <p class="mt-1 truncate text-[11px] font-light uppercase tracking-[0.12em] text-[#4A4F68]">
            {{ title }}
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <div v-if="!isReady" class="text-right font-mono text-[10px] tracking-[0.16em] text-[#4A4F68]">
          <div>{{ progressText }}</div>
          <div>{{ progress }}%</div>
        </div>
        <span v-else class="font-mono text-[10px] tracking-[0.18em] text-[#4A4F68]">
          SECURE_VERIFIED
        </span>
        <button
          type="button"
          class="focus-ring rounded-full border border-white/[0.04] p-2 text-[#4A4F68] transition hover:border-aurora-mint/20 hover:text-[#E6EAF4]"
          aria-label="Pin card"
          @click="$emit('pin')"
        >
          <IconPin />
        </button>
        <button
          type="button"
          class="focus-ring rounded-full border border-white/[0.04] p-2 text-[#4A4F68] transition hover:border-aurora-purple/20 hover:text-[#E6EAF4]"
          aria-label="Minimize card"
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
          class="h-4 overflow-hidden rounded bg-white/[0.04]"
          :class="width"
        >
          <div class="h-full w-1/2 bg-gradient-to-r from-transparent via-white/10 to-transparent animate-shimmer" />
        </div>
        <div class="mt-4 h-px w-full bg-white/[0.06]">
          <div
            class="h-px bg-aurora-purple transition-all duration-500"
            :style="{ width: `${progress}%` }"
          />
        </div>
      </div>

      <div
        class="text-sm font-normal leading-relaxed tracking-wide text-gray-300"
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
import IconMinimize from "./icons/IconMinimize.vue";
import IconPin from "./icons/IconPin.vue";

defineProps({
  agentName: { type: String, default: "" },
  title: { type: String, default: "" },
  progressText: { type: String, default: "Mesh Sync" },
  progress: { type: Number, default: 0 },
  isReady: { type: Boolean, default: false },
  isActive: { type: Boolean, default: false },
  readyClass: { type: String, default: "bg-aurora-mint" },
});

defineEmits(["pin", "minimize"]);
</script>
