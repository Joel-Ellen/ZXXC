<template>
  <section class="mb-6 rounded-[22px] border border-white/[0.04] bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.012))] p-5 shadow-[inset_0_1px_10px_rgba(0,0,0,0.38),0_18px_38px_rgba(0,0,0,0.18)]">
    <div class="mb-5 flex items-start justify-between gap-3">
      <div>
        <p class="text-[10px] font-black uppercase tracking-[0.16em] text-[#4A4F68]">Cold Start Probe</p>
        <h2 class="mt-2 text-xl font-black uppercase tracking-[-0.05em] text-[#F0F3FB]">
          Learning Signal Intake
        </h2>
      </div>
      <div class="text-right text-[11px] font-light text-[#4A4F68]">
        <div>Round {{ collected + 1 }}</div>
        <div>{{ Math.min(collected, total) }}/{{ total }}</div>
      </div>
    </div>

    <div class="mb-5 flex gap-2">
      <span
        v-for="index in total"
        :key="index"
        class="h-px flex-1"
        :class="index <= collected ? 'bg-aurora-mint' : index === collected + 1 ? 'bg-aurora-purple' : 'bg-white/[0.08]'"
      />
    </div>

    <p class="max-w-[42ch] text-base font-light leading-8 text-[#DCE1EE]">
      {{ probe?.question }}
    </p>

    <div class="mt-5 space-y-3">
      <button
        v-for="(option, index) in probe?.options ?? []"
        :key="`${option}-${index}`"
        type="button"
        class="focus-ring w-full rounded-[18px] border px-4 py-3 text-left transition"
        :class="selectedClass(option)"
        @click="toggleOption(option, probe?.option_values?.[index] ?? option)"
      >
        <span class="text-sm font-light text-[#E8ECF6]">{{ option }}</span>
      </button>
    </div>

    <div class="mt-6 flex items-center justify-between gap-4">
      <p class="text-[11px] font-light text-[#4A4F68]">
        {{ probe?.is_multi_select ? "Multi-select is enabled for this intake." : "Single-select response expected." }}
      </p>
      <button
        type="button"
        class="focus-ring rounded-full border border-white/[0.05] bg-[linear-gradient(135deg,rgba(0,242,254,0.26),rgba(127,0,255,0.4))] px-5 py-2 text-[11px] font-black uppercase tracking-[0.14em] text-white transition active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-40"
        :disabled="isDisabled || submitting"
        @click="$emit('submit', selectedValues)"
      >
        {{ submitting ? "Routing" : "Continue" }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  probe: { type: Object, default: null },
  collected: { type: Number, default: 0 },
  total: { type: Number, default: 6 },
  submitting: { type: Boolean, default: false },
});

defineEmits(["submit"]);

const selectedValues = ref([]);

watch(
  () => props.probe,
  () => {
    selectedValues.value = [];
  },
);

const isDisabled = computed(() => selectedValues.value.length === 0);

function toggleOption(optionLabel, optionValue) {
  const value = optionValue ?? optionLabel;
  if (props.probe?.is_multi_select) {
    if (selectedValues.value.includes(value)) {
      selectedValues.value = selectedValues.value.filter((item) => item !== value);
    } else {
      selectedValues.value = [...selectedValues.value, value];
    }
    return;
  }

  selectedValues.value = [value];
}

function selectedClass(optionLabel) {
  const index = props.probe?.options?.indexOf(optionLabel) ?? -1;
  const value = props.probe?.option_values?.[index] ?? optionLabel;
  return selectedValues.value.includes(value)
    ? "border-aurora-mint/30 bg-aurora-mint/8 text-aurora-mint"
    : "border-white/[0.04] bg-transparent hover:border-aurora-purple/25 hover:bg-aurora-purple/[0.04]";
}
</script>
