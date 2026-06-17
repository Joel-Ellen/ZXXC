<template>
  <section class="mb-6 rounded-[22px] border border-subtle bg-card p-5 shadow-card">
    <div class="mb-5 flex items-start justify-between gap-3">
      <div>
        <p class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">冷启动测评</p>
        <h2 class="mt-2 text-xl font-black tracking-tight text-text-primary">
          学习画像采集
        </h2>
      </div>
      <div class="text-right text-[11px] font-light text-text-muted">
        <div>第 {{ collected + 1 }} 轮</div>
        <div>{{ Math.min(collected, total) }}/{{ total }}</div>
      </div>
    </div>

    <div class="mb-5 flex gap-1.5">
      <span
        v-for="index in total"
        :key="index"
        class="h-1 flex-1 rounded-full transition-all duration-300"
        :class="index <= collected ? 'bg-success shadow-[0_0_8px_var(--color-success)]' : index === collected + 1 ? 'bg-secondary' : 'bg-[var(--border-strong)]'"
      />
    </div>

    <p class="max-w-[42ch] text-base font-light leading-8 text-text-secondary">
      {{ probe?.question }}
    </p>

    <div class="mt-5 space-y-3">
      <button
        v-for="(option, index) in probe?.options ?? []"
        :key="`${option}-${index}`"
        type="button"
        class="focus-ring w-full rounded-[16px] border px-4 py-3 text-left transition-all duration-200 active:scale-[0.99]"
        :class="selectedClass(option)"
        @click="toggleOption(option, probe?.option_values?.[index] ?? option)"
      >
        <span class="text-sm font-light text-text-primary">{{ option }}</span>
      </button>
    </div>

    <div class="mt-6 flex items-center justify-between gap-4">
      <p class="text-[11px] font-light text-text-muted">
        {{ probe?.is_multi_select ? "本题支持多选。" : "本题仅支持单选。" }}
      </p>
      <button
        type="button"
        class="focus-ring btn-capsule"
        :disabled="isDisabled || submitting"
        @click="$emit('submit', selectedValues)"
      >
        {{ submitting ? "提交中" : "继续" }}
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
    ? "border-primary/30 bg-primary-soft text-primary"
    : "border-subtle bg-transparent hover:border-secondary/25 hover:bg-card-hover";
}
</script>
