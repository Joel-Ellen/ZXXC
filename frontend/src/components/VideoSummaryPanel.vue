<template>
  <section class="space-y-4" aria-label="视频摘要">
    <div class="workspace-shell-card rounded-[20px] p-4">
      <p class="text-sm leading-7 text-text-secondary">{{ summary }}</p>
      <ul v-if="keyPoints.length" class="mt-4 space-y-2 text-sm leading-6 text-text-secondary">
        <li v-for="(point, pointIndex) in keyPoints" :key="`${resourceId}-point-${pointIndex}`">
          {{ point }}
        </li>
      </ul>
    </div>

    <div v-if="timeline.length" class="workspace-shell-card rounded-[20px] p-4">
      <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">分段提纲</p>
      <div class="mt-3 space-y-3">
        <div
          v-for="(item, index) in timeline"
          :key="`${resourceId}-timeline-${index}`"
          class="workspace-shell-card-soft rounded-[16px] px-4 py-3"
        >
          <p class="text-[11px] font-black uppercase tracking-[0.12em] text-text-muted">{{ item.label }}</p>
          <p class="mt-2 text-sm leading-6 text-text-secondary">{{ item.summary }}</p>
        </div>
      </div>
    </div>

    <div v-if="watchFocus.length || reviewQuestions.length" class="grid gap-4 lg:grid-cols-2">
      <div v-if="watchFocus.length" class="workspace-shell-card rounded-[20px] p-4">
        <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">观看关注点</p>
        <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
          <li v-for="(item, index) in watchFocus" :key="`${resourceId}-watch-${index}`">{{ item }}</li>
        </ul>
      </div>
      <div v-if="reviewQuestions.length" class="workspace-shell-card rounded-[20px] p-4">
        <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">复习问题</p>
        <ul class="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
          <li v-for="(item, index) in reviewQuestions" :key="`${resourceId}-review-q-${index}`">{{ item }}</li>
        </ul>
      </div>
    </div>

    <a
      v-if="videoUrl"
      :href="videoUrl"
      target="_blank"
      rel="noopener noreferrer"
      class="workspace-shell-btn workspace-shell-btn--secondary focus-ring inline-flex min-h-11 items-center px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.10em]"
    >
      打开视频链接
    </a>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { extractTextPreview } from "../utils/markdownPreview.js";

const props = defineProps({
  card: { type: Object, required: true },
});

const metadata = computed(() => {
  const value = props.card?.structured_payload || props.card?.metadata || {};
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
});

const resourceId = computed(() => props.card?.resource_id || props.card?.id || "video-summary");
const summary = computed(() => (
  metadata.value.summary
  || extractTextPreview(props.card?.body_markdown || props.card?.content || "", 190)
));
const keyPoints = computed(() => listMetadata("key_points"));
const timeline = computed(() => listMetadata("timeline"));
const watchFocus = computed(() => listMetadata("watch_focus"));
const reviewQuestions = computed(() => listMetadata("review_questions"));
const videoUrl = computed(() => metadata.value.video_url || "");

function listMetadata(key) {
  return Array.isArray(metadata.value[key]) ? metadata.value[key] : [];
}
</script>
