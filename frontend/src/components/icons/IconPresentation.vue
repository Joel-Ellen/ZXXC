<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d="M3 4h18" />
    <path d="M12 4v3" />
    <rect x="5" y="7" width="14" height="11" rx="1.5" />
    <path d="M9 21v-3" />
    <path d="M15 21v-3" />
    <path d="M9 11h6" />
    <path d="M9 14h4" />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 16 },
});
</script>
