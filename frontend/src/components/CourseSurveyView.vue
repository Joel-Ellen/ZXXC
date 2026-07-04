<template>
  <section class="relative z-10 min-h-screen px-4 py-6 sm:px-6 lg:px-8">
    <div class="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <header class="workspace-shell-card rounded-2xl px-5 py-5 sm:px-6">
        <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div class="min-w-0">
            <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">入课问卷</p>
            <h1 class="mt-2 text-[30px] font-black tracking-tight text-text-primary">
              {{ course?.title_cn || "课程画像问卷" }}
            </h1>
            <p class="mt-3 max-w-3xl text-sm leading-7 text-text-secondary">
              问卷结果会回写课程画像、用户资料和初始学习状态。这里用整页表单，不做弹窗压缩。
            </p>
          </div>

          <button
            type="button"
            class="workspace-shell-btn focus-ring px-4 py-2.5 text-sm font-semibold"
            @click="$emit('cancel')"
          >
            返回课程目录
          </button>
        </div>
      </header>

      <section class="workspace-shell-card rounded-2xl px-5 py-5 sm:px-6">
        <div class="grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">显示名称</span>
            <input
              :value="draft.profilePatch.display_name"
              type="text"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @input="patchProfile('display_name', $event.target.value)"
            />
          </label>
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">邮箱</span>
            <input
              :value="draft.profilePatch.email"
              type="email"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @input="patchProfile('email', $event.target.value)"
            />
          </label>
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">学校</span>
            <input
              :value="draft.profilePatch.university"
              type="text"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @input="patchProfile('university', $event.target.value)"
            />
          </label>
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">专业</span>
            <input
              :value="draft.profilePatch.major"
              type="text"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @input="patchProfile('major', $event.target.value)"
            />
          </label>
        </div>
      </section>

      <section
        v-for="section in survey.sections || []"
        :key="section.id"
        class="workspace-shell-card rounded-2xl px-5 py-5 sm:px-6"
      >
        <h2 class="text-xl font-black tracking-tight text-text-primary">{{ section.title }}</h2>
        <p class="mt-2 text-sm leading-7 text-text-secondary">{{ section.description }}</p>

        <div class="mt-5 space-y-6">
          <div
            v-for="question in section.questions || []"
            :key="question.id"
            class="workspace-shell-card-soft rounded-2xl px-4 py-4"
          >
            <div class="flex items-center gap-2">
              <p class="text-sm font-semibold text-text-primary">{{ question.label }}</p>
              <span v-if="question.required" class="text-[11px] font-semibold text-primary">必填</span>
            </div>

            <div v-if="question.type === 'single_choice'" class="mt-4 grid gap-2">
              <button
                v-for="option in question.options || []"
                :key="option"
                type="button"
                class="focus-ring rounded-2xl border px-4 py-3 text-left text-sm transition-all"
                :class="singleChoiceClass(question.id, option)"
                @click="setSingleChoice(question.id, option)"
              >
                {{ option }}
              </button>
            </div>

            <div v-else-if="question.type === 'multi_choice'" class="mt-4 grid gap-2">
              <button
                v-for="option in question.options || []"
                :key="option"
                type="button"
                class="focus-ring rounded-2xl border px-4 py-3 text-left text-sm transition-all"
                :class="multiChoiceClass(question.id, option)"
                @click="toggleMultiChoice(question.id, option)"
              >
                {{ option }}
              </button>
            </div>

            <textarea
              v-else
              :value="draft.answers[question.id] || ''"
              :placeholder="question.placeholder || '请输入你的回答'"
              class="workspace-shell-input focus-ring mt-4 min-h-[136px] w-full rounded-2xl px-4 py-3 text-sm leading-7 text-text-primary"
              @input="setLongText(question.id, $event.target.value)"
            />
          </div>
        </div>
      </section>

      <footer class="workspace-shell-card rounded-2xl px-5 py-5 sm:px-6">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <p class="text-sm leading-7 text-text-secondary">
            提交后会完成选课、写入课程画像，并把用户资料同步到数据库。
          </p>
          <div class="flex flex-wrap items-center gap-2">
            <button
              type="button"
              class="workspace-shell-btn focus-ring px-4 py-2.5 text-sm font-semibold"
              @click="$emit('cancel')"
            >
              取消
            </button>
            <button
              type="button"
              class="workspace-shell-btn workspace-shell-btn--accent focus-ring px-4 py-2.5 text-sm font-semibold"
              :disabled="busy || !isComplete"
              @click="$emit('submit')"
            >
              提交问卷并加入课程
            </button>
          </div>
        </div>
      </footer>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  course: { type: Object, default: null },
  survey: { type: Object, default: () => ({ sections: [] }) },
  draft: { type: Object, required: true },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits(["update-draft", "submit", "cancel"]);

const isComplete = computed(() =>
  (props.survey.sections || []).every((section) =>
    (section.questions || []).every((question) => {
      if (!question.required) {
        return true;
      }
      const value = props.draft.answers?.[question.id];
      if (question.type === "multi_choice") {
        return Array.isArray(value) && value.length > 0;
      }
      return typeof value === "string" ? value.trim().length > 0 : Boolean(value);
    }),
  ),
);

function updateDraft(next) {
  emit("update-draft", next);
}

function patchProfile(key, value) {
  updateDraft({
    ...props.draft,
    profilePatch: {
      ...(props.draft.profilePatch || {}),
      [key]: value,
    },
  });
}

function setSingleChoice(questionId, option) {
  updateDraft({
    ...props.draft,
    answers: {
      ...(props.draft.answers || {}),
      [questionId]: option,
    },
  });
}

function toggleMultiChoice(questionId, option) {
  const current = Array.isArray(props.draft.answers?.[questionId]) ? props.draft.answers[questionId] : [];
  const nextValues = current.includes(option)
    ? current.filter((item) => item !== option)
    : [...current, option];
  updateDraft({
    ...props.draft,
    answers: {
      ...(props.draft.answers || {}),
      [questionId]: nextValues,
    },
  });
}

function setLongText(questionId, value) {
  updateDraft({
    ...props.draft,
    answers: {
      ...(props.draft.answers || {}),
      [questionId]: value,
    },
  });
}

function singleChoiceClass(questionId, option) {
  return props.draft.answers?.[questionId] === option
    ? "border-primary/35 bg-primary-soft text-primary"
    : "border-subtle bg-space-panel text-text-secondary hover:border-hover hover:text-text-primary";
}

function multiChoiceClass(questionId, option) {
  return Array.isArray(props.draft.answers?.[questionId]) && props.draft.answers[questionId].includes(option)
    ? "border-primary/35 bg-primary-soft text-primary"
    : "border-subtle bg-space-panel text-text-secondary hover:border-hover hover:text-text-primary";
}
</script>
