<template>
  <component :is="resolvedIcon" :size="size" aria-hidden="true" />
</template>

<script setup>
import { computed } from "vue";
import IconDoc from "./IconDoc.vue";
import IconRadar from "./IconRadar.vue";
import IconSettings from "./IconSettings.vue";
import IconTree from "./IconTree.vue";

const props = defineProps({
  courseId: { type: String, default: "" },
  icon: { type: String, default: "" },
  size: { type: [Number, String], default: 24 },
});

const ICON_COMPONENTS = {
  algorithm: IconTree,
  book: IconDoc,
  document: IconDoc,
  network: IconRadar,
  python: IconDoc,
  settings: IconSettings,
  system: IconSettings,
  ai: IconRadar,
};

const COURSE_ICON_KEYS = {
  data_structures: "algorithm",
  operating_systems: "system",
  computer_networks: "network",
  machine_learning: "ai",
  python_programming: "python",
};

function normalizeIconKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z]/g, "");
}

const resolvedIcon = computed(() => {
  const normalizedIcon = normalizeIconKey(props.icon);
  const mappedByIcon = ICON_COMPONENTS[normalizedIcon];
  if (mappedByIcon) return mappedByIcon;

  const normalizedCourseId = String(props.courseId || "").trim().toLowerCase();
  const mappedByCourse = ICON_COMPONENTS[COURSE_ICON_KEYS[normalizedCourseId]];
  return mappedByCourse || IconDoc;
});
</script>
