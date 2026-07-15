<template>
  <section class="relative z-10 min-h-screen px-4 py-6 sm:px-6 lg:px-8">
    <div class="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <header class="workspace-shell-card rounded-2xl px-5 py-5 sm:px-6">
        <div class="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div class="min-w-0">
            <p class="text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">用户管理</p>
            <h1 class="mt-2 text-[30px] font-black tracking-tight text-text-primary">维护你的学习资料</h1>
            <p class="mt-3 max-w-3xl text-sm leading-7 text-text-secondary">
              这些信息会作为新增课程问卷的默认值，也会参与资源风格、学习节奏和练习强度的初始决策。
            </p>
          </div>

          <button
            type="button"
            class="workspace-shell-btn focus-ring px-4 py-2.5 text-sm font-semibold"
            @click="$emit('back')"
          >
            返回课程管理
          </button>
        </div>
      </header>

      <section class="workspace-shell-card rounded-2xl px-5 py-5 sm:px-6">
        <div class="grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">显示名称</span>
            <input
              :value="draft.display_name"
              type="text"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @input="patch('display_name', $event.target.value)"
            />
          </label>
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">邮箱</span>
            <input
              :value="draft.email"
              type="email"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @input="patch('email', $event.target.value)"
            />
          </label>
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">学校</span>
            <input
              :value="draft.university"
              type="text"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @input="patch('university', $event.target.value)"
            />
          </label>
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">专业</span>
            <input
              :value="draft.major"
              type="text"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @input="patch('major', $event.target.value)"
            />
          </label>
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">年级</span>
            <input
              :value="draft.grade"
              type="text"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @input="patch('grade', $event.target.value)"
            />
          </label>
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">每周学习时长</span>
            <input
              :value="draft.weekly_study_hours"
              type="number"
              min="1"
              max="80"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @input="patch('weekly_study_hours', Number($event.target.value || 0))"
            />
          </label>
        </div>

        <label class="mt-4 block">
          <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">学习目标</span>
          <textarea
            :value="draft.learning_goal"
            class="workspace-shell-input focus-ring min-h-[140px] w-full rounded-2xl px-4 py-3 text-sm leading-7 text-text-primary"
            @input="patch('learning_goal', $event.target.value)"
          />
        </label>
      </section>

      <section class="workspace-shell-card rounded-2xl px-5 py-5 sm:px-6">
        <h2 class="text-xl font-black tracking-tight text-text-primary">学习偏好</h2>
        <div class="mt-5 grid gap-4 md:grid-cols-3">
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">资源风格</span>
            <select
              :value="draft.preferred_resource_style"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @change="patch('preferred_resource_style', $event.target.value)"
            >
              <option value="textual">概念优先</option>
              <option value="code_first">代码优先</option>
              <option value="interactive">练习优先</option>
              <option value="summary_first">总结优先</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">学习节奏</span>
            <select
              :value="draft.preferred_pace"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @change="patch('preferred_pace', $event.target.value)"
            >
              <option value="gentle">平缓</option>
              <option value="steady">稳定</option>
              <option value="intensive">高强度</option>
            </select>
          </label>
          <label class="block">
            <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.14em] text-text-muted">练习强度</span>
            <select
              :value="draft.preferred_practice_intensity"
              class="workspace-shell-input focus-ring w-full rounded-2xl px-4 py-3 text-sm text-text-primary"
              @change="patch('preferred_practice_intensity', $event.target.value)"
            >
              <option value="light">轻量</option>
              <option value="balanced">均衡</option>
              <option value="intensive">高频训练</option>
            </select>
          </label>
        </div>
      </section>

      <footer class="workspace-shell-card rounded-2xl px-5 py-5 sm:px-6">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <p class="text-sm leading-7 text-text-secondary">
            保存后刷新页面仍会保留，新增课程时会自动带入这些资料。
          </p>
          <div class="flex gap-2">
            <button
              type="button"
              class="workspace-shell-btn focus-ring px-4 py-2.5 text-sm font-semibold"
              @click="$emit('back')"
            >
              返回
            </button>
            <button
              type="button"
              class="workspace-shell-btn workspace-shell-btn--accent focus-ring px-4 py-2.5 text-sm font-semibold"
              :disabled="busy"
              @click="$emit('save', draft)"
            >
              保存资料
            </button>
          </div>
        </div>
      </footer>
    </div>
  </section>
</template>

<script setup>
import { reactive, watch } from "vue";

const props = defineProps({
  profile: { type: Object, required: true },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits(["save", "back"]);

const draft = reactive({ ...props.profile });

watch(
  () => props.profile,
  (next) => {
    Object.assign(draft, next);
  },
  { deep: true, immediate: true },
);

function patch(key, value) {
  draft[key] = value;
}
</script>
