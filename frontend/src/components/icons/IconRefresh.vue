<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d="M20 11a8.1 8.1 0 0 0-14-4.9L4 8" />
    <path d="M4 4v4h4" />
    <path d="M4 13a8.1 8.1 0 0 0 14 4.9L20 16" />
    <path d="M20 20v-4h-4" />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 16 },
});
</script>
