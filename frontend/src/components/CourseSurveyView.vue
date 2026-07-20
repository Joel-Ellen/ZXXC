<template>
  <section class="course-survey-view relative z-10 flex items-center justify-center px-4 py-6 sm:px-6 sm:py-8">
    <div class="mx-auto w-full max-w-2xl">

      <!-- Header -->
      <header class="mb-6 flex min-w-0 items-start justify-between gap-3 sm:items-center">
        <div class="flex min-w-0 items-center gap-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary-soft text-primary">
            <IconUser :size="18" />
          </div>
          <div class="min-w-0">
            <p class="text-[10px] font-black uppercase tracking-[0.14em] text-text-muted">智能画像构建</p>
            <h1 class="text-[18px] font-black tracking-tight text-text-primary">
              {{ course?.title_cn || "课程" }} · 个性化入课
            </h1>
          </div>
        </div>
        <button type="button" class="workspace-shell-btn focus-ring px-3 py-2 text-[11px] font-semibold" @click="$emit('cancel')">
          返回
        </button>
      </header>

      <!-- Progress bar -->
      <div class="mb-6">
        <div class="mb-1.5 flex items-center justify-between">
          <span class="text-[11px] font-semibold text-text-muted">问题 {{ currentStepIndex + 1 }} / {{ allSteps.length }}</span>
          <span class="text-[11px] font-semibold text-primary">{{ progressPct }}%</span>
        </div>
        <div class="h-1.5 overflow-hidden rounded-full bg-space-line">
          <div class="h-full rounded-full bg-primary status-bar-fill transition-all duration-500"
               :style="{ width: progressPct + '%' }" />
        </div>
      </div>

      <!-- Chat conversation area -->
      <div class="survey-chat-area mb-5 space-y-4 rounded-2xl border border-subtle bg-space-panel p-4 sm:p-5">

        <!-- Answered steps (history) -->
        <template v-for="(step, idx) in answeredSteps" :key="step.id">
          <!-- System question bubble -->
          <div class="flex justify-start animate-slideUp" :style="{ animationDelay: '0ms' }">
            <div class="survey-bubble survey-bubble--system max-w-[88%]">
              <p class="text-[10px] font-black uppercase tracking-[0.12em] text-primary mb-1.5">EduAgent</p>
              <p class="text-sm leading-7 text-text-primary">{{ step.label }}</p>
            </div>
          </div>
          <!-- User answer bubble -->
          <div class="flex justify-end">
            <div class="survey-bubble survey-bubble--user max-w-[88%]">
              <p class="text-sm text-text-primary">{{ formatAnswer(step) }}</p>
            </div>
          </div>
        </template>

        <!-- Current question -->
        <div v-if="currentStep" class="flex justify-start animate-slideUp">
          <div class="survey-bubble survey-bubble--system max-w-[88%]">
            <p class="text-[10px] font-black uppercase tracking-[0.12em] text-primary mb-1.5">EduAgent</p>
            <p class="text-sm leading-7 text-text-primary">{{ currentStep.label }}</p>
            <p v-if="!currentStep.required" class="mt-1 text-[11px] text-text-muted">（可选）</p>
          </div>
        </div>

        <!-- Done message -->
        <div v-if="isAllAnswered" class="flex justify-start animate-slideUp">
          <div class="survey-bubble survey-bubble--system max-w-[88%]">
            <p class="text-[10px] font-black uppercase tracking-[0.12em] text-primary mb-1.5">EduAgent</p>
            <p class="text-sm leading-7 text-text-primary">
              太好了！我已经了解你的学习背景。点击下方按钮开始你的个性化学习之旅。
            </p>
          </div>
        </div>
      </div>

      <!-- Answer input area -->
      <div v-if="currentStep && !isAllAnswered" class="animate-slideUp">

        <!-- Single choice -->
        <div v-if="currentStep.type === 'single_choice'" class="grid gap-2 sm:grid-cols-2">
          <button
            v-for="option in currentStep.options || []"
            :key="option"
            type="button"
            class="survey-option focus-ring text-left text-sm"
            :class="draftAnswerFor(currentStep.id) === option ? 'survey-option--selected' : ''"
            @click="pickAndAdvance(currentStep.id, option)"
          >
            {{ option }}
          </button>
        </div>

        <!-- Multi choice -->
        <div v-else-if="currentStep.type === 'multi_choice'" class="space-y-2">
          <div class="grid gap-2 sm:grid-cols-2">
            <button
              v-for="option in currentStep.options || []"
              :key="option"
              type="button"
              class="survey-option focus-ring text-left text-sm"
              :class="multiSelected(currentStep.id, option) ? 'survey-option--selected' : ''"
              @click="toggleMultiChoice(currentStep.id, option)"
            >
              {{ option }}
            </button>
          </div>
          <button
            type="button"
            class="mt-3 workspace-shell-btn workspace-shell-btn--accent focus-ring w-full py-3 text-sm font-semibold"
            :disabled="!hasMultiAnswer(currentStep.id)"
            @click="advanceStep"
          >
            确认并继续
            <IconArrowRight :size="14" />
          </button>
        </div>

        <!-- Text input -->
        <div v-else class="space-y-3">
          <input
            v-if="currentStep.inputType !== 'textarea'"
            :value="draftAnswerFor(currentStep.id)"
            :type="currentStep.inputType || 'text'"
            :placeholder="currentStep.placeholder || '请输入…'"
            class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
            @input="setAnswer(currentStep.id, $event.target.value)"
            @keydown.enter="advanceStep"
          />
          <textarea
            v-else
            :value="draftAnswerFor(currentStep.id)"
            :placeholder="currentStep.placeholder || '请输入…'"
            rows="3"
            class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm leading-7 text-text-primary"
            @input="setAnswer(currentStep.id, $event.target.value)"
          />
          <div class="flex gap-2">
            <button
              v-if="!currentStep.required"
              type="button"
              class="workspace-shell-btn focus-ring flex-1 py-3 text-sm font-semibold"
              @click="skipStep"
            >
              跳过
            </button>
            <button
              type="button"
              class="workspace-shell-btn workspace-shell-btn--accent focus-ring flex-1 py-3 text-sm font-semibold"
              :disabled="currentStep.required && !draftAnswerFor(currentStep.id)"
              @click="advanceStep"
            >
              确认并继续
              <IconArrowRight :size="14" />
            </button>
          </div>
        </div>
      </div>

      <!-- Submit footer -->
      <div v-if="isAllAnswered" class="animate-slideUp">
        <button
          type="button"
          class="btn-ripple w-full btn-primary py-4 text-sm font-bold tracking-[0.04em]"
          :disabled="busy"
          @click="$emit('submit')"
        >
          <span v-if="busy" class="flex items-center justify-center gap-2">
            <span class="generating-dot" /><span class="generating-dot" /><span class="generating-dot" />
          </span>
          <span v-else>
            <IconStar :size="14" filled class="inline-block mr-1 align-text-bottom" />
            生成个性化学习路径</span>
        </button>
      </div>

    </div>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import IconArrowRight from "./icons/IconArrowRight.vue";
import IconStar from "./icons/IconStar.vue";
import IconUser from "./icons/IconUser.vue";

const props = defineProps({
  course:  { type: Object, default: null },
  survey:  { type: Object, default: () => ({ sections: [] }) },
  draft:   { type: Object, required: true },
  busy:    { type: Boolean, default: false },
});

const emit = defineEmits(["update-draft", "submit", "cancel"]);

// ── Build flat step list from survey + profile fields ─────────────────
const allSteps = computed(() => {
  const profileSteps = [
    { id: "__display_name", label: "你叫什么名字？（昵称或真名均可）", type: "text", required: false, placeholder: "例：小明", _profile: "display_name" },
    { id: "__university",   label: "你就读于哪所学校？", type: "text", required: false, placeholder: "例：北京大学", _profile: "university" },
    { id: "__major",        label: "你的专业方向是什么？", type: "text", required: false, placeholder: "例：计算机科学与技术", _profile: "major" },
  ];

  const surveySteps = (props.survey.sections || []).flatMap(
    (sec) => (sec.questions || []).map((q) => ({ ...q, _profile: null })),
  );

  return [...profileSteps, ...surveySteps];
});

// ── Step cursor ───────────────────────────────────────────────────────
const currentStepIndex = ref(0);

const currentStep = computed(() => allSteps.value[currentStepIndex.value] ?? null);
const answeredSteps = computed(() => allSteps.value.slice(0, currentStepIndex.value));
const isAllAnswered = computed(() => currentStepIndex.value >= allSteps.value.length);
const progressPct = computed(() =>
  allSteps.value.length ? Math.round((currentStepIndex.value / allSteps.value.length) * 100) : 0
);

// ── Answer helpers ────────────────────────────────────────────────────
function draftAnswerFor(id) {
  if (id.startsWith("__")) {
    const key = id.replace("__", "");
    return props.draft.profilePatch?.[key] ?? "";
  }
  return props.draft.answers?.[id] ?? "";
}

function multiSelected(id, option) {
  const v = props.draft.answers?.[id];
  return Array.isArray(v) && v.includes(option);
}

function hasMultiAnswer(id) {
  const v = props.draft.answers?.[id];
  return Array.isArray(v) && v.length > 0;
}

function setAnswer(id, value) {
  if (id.startsWith("__")) {
    const key = id.replace("__", "");
    emit("update-draft", {
      ...props.draft,
      profilePatch: { ...(props.draft.profilePatch || {}), [key]: value },
    });
  } else {
    emit("update-draft", {
      ...props.draft,
      answers: { ...(props.draft.answers || {}), [id]: value },
    });
  }
}

function toggleMultiChoice(id, option) {
  const current = Array.isArray(props.draft.answers?.[id]) ? props.draft.answers[id] : [];
  const next = current.includes(option) ? current.filter((x) => x !== option) : [...current, option];
  emit("update-draft", {
    ...props.draft,
    answers: { ...(props.draft.answers || {}), [id]: next },
  });
}

// ── Navigation ────────────────────────────────────────────────────────
function pickAndAdvance(id, option) {
  setAnswer(id, option);
  setTimeout(advanceStep, 180);
}

function advanceStep() {
  if (currentStepIndex.value < allSteps.value.length) {
    currentStepIndex.value += 1;
    // Scroll chat area to bottom
    setTimeout(() => {
      const el = document.querySelector(".survey-chat-area");
      if (el) el.scrollTop = el.scrollHeight;
    }, 50);
  }
}

function skipStep() {
  advanceStep();
}

// ── Format answer for display in history ─────────────────────────────
function formatAnswer(step) {
  const v = draftAnswerFor(step.id);
  if (Array.isArray(v)) return v.join("、") || "（已跳过）";
  return v || "（已跳过）";
}
</script>

<style scoped>
.course-survey-view {
  min-height: 100vh;
  min-height: 100dvh;
  padding-top: max(1.5rem, env(safe-area-inset-top, 0px));
  padding-bottom: max(1.5rem, env(safe-area-inset-bottom, 0px));
}

.survey-chat-area {
  min-height: clamp(16rem, 42dvh, 21.25rem);
  max-height: min(32.5rem, 56dvh);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.survey-bubble {
  border-radius: 1.125rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-subtle);
}

.survey-bubble--system {
  border-top-left-radius: 0.25rem;
  background: color-mix(in srgb, var(--color-primary-soft) 50%, var(--space-elevated));
  border-color: color-mix(in srgb, var(--color-primary) 18%, var(--border-subtle));
}

.survey-bubble--user {
  border-top-right-radius: 0.25rem;
  background: color-mix(in srgb, var(--color-secondary-soft) 50%, var(--space-elevated));
  border-color: color-mix(in srgb, var(--color-secondary) 18%, var(--border-subtle));
}

.survey-option {
  border: 1px solid var(--border-subtle);
  border-radius: 1rem;
  padding: 0.75rem 1rem;
  background: var(--space-elevated);
  color: var(--text-secondary);
  transition: all 180ms cubic-bezier(0.16, 1, 0.3, 1);
}

.survey-option:hover {
  border-color: var(--border-hover);
  background: var(--card-bg-hover);
  color: var(--text-primary);
  transform: translateY(-1px);
}

.survey-option--selected {
  border-color: color-mix(in srgb, var(--color-primary) 40%, var(--border-subtle));
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
  font-weight: 600;
}

@media (max-height: 700px) {
  .course-survey-view {
    align-items: flex-start;
  }

  .survey-chat-area {
    min-height: 12rem;
    max-height: 42dvh;
  }
}
</style>
