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
    <path d="M12 5v14" />
    <path d="M7 10h10" />
    <path d="M7 19h10" />
    <circle cx="12" cy="5" r="2.5" />
    <circle cx="7" cy="10" r="2.5" />
    <circle cx="17" cy="10" r="2.5" />
    <circle cx="7" cy="19" r="2.5" />
    <circle cx="17" cy="19" r="2.5" />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 18 },
});
</script>
