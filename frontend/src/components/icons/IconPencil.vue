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
    <path d="M17.2 2.8a2.68 2.68 0 0 1 3.8 3.8L7.3 20.3a2 2 0 0 1-.83.5l-4 1.2a.5.5 0 0 1-.62-.62l1.2-4a2 2 0 0 1 .5-.83z" />
    <path d="m14.5 5.5 4 4" />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 16 },
});
</script>
