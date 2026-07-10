<template>
  <RouterView />
</template>

<script setup>
import { RouterView } from "vue-router";
import { useTheme } from "./composables/useTheme.js";

useTheme();
</script>
