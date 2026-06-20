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
    <path d="M12 3 4 7.5v9L12 21l8-4.5v-9z" />
    <path d="M12 7.5 8 9.8v4.4l4 2.3 4-2.3V9.8z" />
    <path d="M12 3v4.5" />
    <path d="M4 7.5 8 9.8" />
    <path d="M20 7.5 16 9.8" />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 18 },
});
</script>
