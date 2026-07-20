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
    <path d="M11.5 3.6a.53.53 0 0 1 1 0l1.6 4.9a2 2 0 0 0 1.4 1.4l4.9 1.6a.53.53 0 0 1 0 1l-4.9 1.6a2 2 0 0 0-1.4 1.4l-1.6 4.9a.53.53 0 0 1-1 0l-1.6-4.9a2 2 0 0 0-1.4-1.4l-4.9-1.6a.53.53 0 0 1 0-1l4.9-1.6a2 2 0 0 0 1.4-1.4z" />
    <path d="M19 3v4" />
    <path d="M21 5h-4" />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 16 },
});
</script>
