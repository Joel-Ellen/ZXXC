<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    :fill="filled ? 'currentColor' : 'none'"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d="M6 3.75A1.75 1.75 0 0 1 7.75 2h8.5A1.75 1.75 0 0 1 18 3.75V20l-6-3.5L6 20V3.75Z" />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 16 },
  filled: { type: Boolean, default: false },
});
</script>
