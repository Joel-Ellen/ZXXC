<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d="M15 4 20 9" />
    <path d="M8 11 3 16" />
    <path d="m14 5-9 9" />
    <path d="M11 8l5 5" />
    <path d="M7 17l-2 4 4-2" />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 16 },
});
</script>
