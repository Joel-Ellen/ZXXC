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
    <path d="M6 12h12" />
    <path d="M12 6v12" transform="rotate(45 12 12)" />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 16 },
});
</script>
