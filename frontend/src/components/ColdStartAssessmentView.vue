<template>
  <main class="cold-start-view relative z-10">
    <section class="cold-start-view__content" aria-labelledby="cold-start-title">
      <header class="cold-start-view__header">
        <div class="cold-start-view__mark" aria-hidden="true">EA</div>
        <div class="min-w-0">
          <p class="text-xs font-semibold text-primary">{{ courseTitle }}</p>
          <h1 id="cold-start-title" class="mt-1 text-xl font-black text-text-primary sm:text-2xl">
            入学能力测试
          </h1>
        </div>
        <span class="cold-start-view__user">{{ userLabel }}</span>
      </header>

      <ProbeDeck
        class="cold-start-view__deck"
        :probe="probe"
        :collected="collected"
        :total="total"
        :submitting="submitting"
        @submit="$emit('submit', $event)"
      />
    </section>
  </main>
</template>

<script setup>
import { computed } from "vue";
import ProbeDeck from "./ProbeDeck.vue";

const props = defineProps({
  user: { type: Object, default: null },
  activeCourse: { type: Object, default: null },
  probe: { type: Object, default: null },
  collected: { type: Number, default: 0 },
  total: { type: Number, default: 6 },
  submitting: { type: Boolean, default: false },
});

defineEmits(["submit"]);

const courseTitle = computed(() => props.activeCourse?.title_cn || "当前课程");
const userLabel = computed(() => props.user?.display_name || props.user?.user_id || "学习者");
</script>

<style scoped>
.cold-start-view {
  display: grid;
  min-height: 100vh;
  min-height: 100dvh;
  place-items: center;
  overflow-y: auto;
  padding:
    max(1.25rem, env(safe-area-inset-top, 0px))
    max(1rem, env(safe-area-inset-right, 0px))
    max(1.25rem, env(safe-area-inset-bottom, 0px))
    max(1rem, env(safe-area-inset-left, 0px));
}

.cold-start-view__content {
  width: min(100%, 46rem);
}

.cold-start-view__header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.85rem;
  margin-bottom: 1rem;
  padding-inline: 0.25rem;
}

.cold-start-view__mark {
  display: inline-flex;
  width: 2.75rem;
  height: 2.75rem;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  background: var(--color-primary);
  color: var(--color-primary-text);
  font-size: 0.78rem;
  font-weight: 900;
}

.cold-start-view__user {
  max-width: 10rem;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cold-start-view__deck {
  margin-bottom: 0;
}

@media (max-width: 479px) {
  .cold-start-view {
    place-items: start center;
  }

  .cold-start-view__header {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .cold-start-view__user {
    display: none;
  }
}
</style>
