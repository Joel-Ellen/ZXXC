<template>
  <AppPageFrame>
    <section class="px-4 py-6 sm:px-6 lg:px-8">
      <div class="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <header class="workspace-shell-card rounded-xl px-5 py-6 sm:px-6">
          <p class="text-xs font-semibold text-text-muted">界面设置</p>
          <h1 class="mt-2 text-2xl font-black text-text-primary">阅读与显示偏好</h1>
          <p class="mt-3 text-sm leading-7 text-text-secondary">保存后会写入当前浏览器，并在下次进入学习页时恢复。</p>
        </header>

        <section class="workspace-shell-card rounded-xl px-5 py-5 sm:px-6">
          <h2 class="text-lg font-black text-text-primary">学习工作台</h2>
          <fieldset class="mt-4 space-y-3 text-sm text-text-secondary">
            <legend class="sr-only">学习工作台显示设置</legend>
            <label class="flex min-h-11 cursor-pointer items-center justify-between gap-4"><span>高对比度</span><input v-model="preferences.highContrast" type="checkbox" class="h-5 w-5" /></label>
            <label class="flex min-h-11 cursor-pointer items-center justify-between gap-4"><span>减少动态效果</span><input v-model="preferences.reduceMotion" type="checkbox" class="h-5 w-5" /></label>
            <label class="block"><span>正文字号：{{ preferences.fontSize }}px</span><input v-model.number="preferences.fontSize" class="mt-2 min-h-11 w-full" type="range" min="14" max="20" step="1" /></label>
          </fieldset>
          <button type="button" class="btn-primary focus-ring mt-6 min-h-11 px-4 py-2.5 text-sm font-semibold" @click="save">保存设置</button>
        </section>
      </div>
    </section>
    <p
      v-if="notice"
      class="fixed bottom-5 left-1/2 z-40 -translate-x-1/2 rounded-lg border bg-space-panel px-4 py-3 text-sm text-text-primary shadow-lg"
      :class="noticeIsError ? 'border-error/40' : 'border-success/40'"
      :role="noticeIsError ? 'alert' : 'status'"
    >
      {{ notice }}
    </p>
  </AppPageFrame>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from "vue";
import AppPageFrame from "../components/AppPageFrame.vue";

const PREFERENCES_KEY = "eduagent-workspace-preferences";
const notice = ref("");
const noticeIsError = ref(false);
const preferences = reactive({ highContrast: false, reduceMotion: false, fontSize: 16 });
let noticeTimer = null;

onMounted(() => {
  try {
    const saved = JSON.parse(window.localStorage.getItem(PREFERENCES_KEY) || "{}");
    preferences.highContrast = Boolean(saved.highContrast);
    preferences.reduceMotion = Boolean(saved.reduceMotion);
    preferences.fontSize = typeof saved.fontSize === "number" ? saved.fontSize : 16;
  } catch {
    // Defaults are already applied when browser storage is unavailable.
  }
});

onBeforeUnmount(() => {
  if (noticeTimer) window.clearTimeout(noticeTimer);
});

function save() {
  try {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ ...preferences }));
    showNotice("界面设置已保存。", false);
  } catch {
    showNotice("当前浏览器无法保存界面设置。", true);
  }
}

function showNotice(message, isError) {
  if (noticeTimer) window.clearTimeout(noticeTimer);
  notice.value = message;
  noticeIsError.value = isError;
  noticeTimer = window.setTimeout(() => {
    notice.value = "";
    noticeTimer = null;
  }, 3000);
}
</script>
