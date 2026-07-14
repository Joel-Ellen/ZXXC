<template>
  <div class="auth-view relative z-10 flex items-center justify-center px-3 py-8 sm:px-4 sm:py-12 animate-fadeIn">
    <div class="w-full max-w-md">
      <!-- Logo -->
      <div class="mb-7 text-center sm:mb-10">
        <div class="relative mb-4 inline-flex h-16 w-16 items-center justify-center overflow-hidden rounded-2xl shadow-glow sm:mb-5 sm:h-20 sm:w-20">
          <div class="absolute inset-0 bg-gradient-to-br from-primary to-secondary opacity-90" />
          <div class="absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.25),transparent)]" />
          <span class="relative text-white text-2xl font-black">EA</span>
        </div>
        <h1 class="mb-2 text-2xl font-black tracking-tight text-text-primary sm:text-3xl">EduAgent</h1>
        <p class="text-sm text-text-secondary">个性化多智能体学习系统</p>
      </div>

      <!-- 卡片 -->
      <div class="glass-card rounded-2xl p-4 sm:p-7">
        <!-- 标签切换 -->
        <div class="flex mb-7 p-1 rounded-xl bg-card border border-subtle">
          <button
            type="button"
            :class="mode === 'login' ? 'bg-card-hover text-text-primary shadow-lg shadow-black/20' : 'text-text-muted hover:text-text-secondary'"
            class="min-h-11 flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200"
            @click="selectMode('login')"
          >登录</button>
          <button
            type="button"
            :class="mode === 'register' ? 'bg-card-hover text-text-primary shadow-lg shadow-black/20' : 'text-text-muted hover:text-text-secondary'"
            class="min-h-11 flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200"
            @click="selectMode('register')"
          >注册</button>
        </div>

        <!-- 表单 -->
        <form @submit.prevent="onSubmit" class="space-y-5">
          <!-- 用户名 -->
          <div>
            <label for="auth-user-id" class="block text-xs font-semibold text-text-secondary mb-1.5">用户名</label>
            <input
              id="auth-user-id"
              v-model="form.userId"
              type="text"
              required
              minlength="3"
              placeholder="请输入用户名"
              class="w-full px-4 py-3 bg-input border border-subtle rounded-xl text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20 transition"
            />
          </div>

          <!-- 邮箱 (仅注册) -->
          <div v-if="mode === 'register'">
            <label for="auth-email" class="block text-xs font-semibold text-text-secondary mb-1.5">邮箱</label>
            <input
              id="auth-email"
              v-model="form.email"
              type="email"
              required
              placeholder="请输入邮箱"
              class="w-full px-4 py-3 bg-input border border-subtle rounded-xl text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20 transition"
            />
          </div>

          <!-- 密码 -->
          <div>
            <label for="auth-password" class="block text-xs font-semibold text-text-secondary mb-1.5">密码</label>
            <input
              id="auth-password"
              v-model="form.password"
              type="password"
              required
              minlength="8"
              placeholder="至少 8 个字符"
              class="w-full px-4 py-3 bg-input border border-subtle rounded-xl text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20 transition"
            />
          </div>

          <!-- 验证码 -->
          <div>
            <label for="auth-captcha" class="block text-xs font-semibold text-text-secondary mb-1.5">验证码</label>
            <div class="captcha-row">
              <input
                id="auth-captcha"
                v-model="form.captchaAnswer"
                type="text"
                required
                placeholder="计算结果"
                class="min-w-0 w-full px-4 py-3 bg-input border border-subtle rounded-xl text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20 transition"
              />
              <div
                class="captcha-preview h-[46px] bg-space-surface rounded-xl cursor-pointer overflow-hidden border border-subtle hover:border-primary/40 transition"
                v-html="captchaSvg"
                @click="fetchCaptcha"
                title="点击刷新验证码"
              ></div>
            </div>
          </div>

          <!-- 错误提示 -->
          <div
            v-if="errorMsg"
            class="flex items-center justify-between gap-3 rounded-xl border border-error/20 bg-error-soft px-3 py-2.5 text-xs text-error"
            role="alert"
          >
            <span>{{ errorMsg }}</span>
            <button
              type="button"
              class="focus-ring shrink-0 rounded-lg px-2 py-1 font-semibold"
              :disabled="loading"
              @click="onSubmit"
            >重试</button>
          </div>

          <!-- 提交按钮 -->
          <button
            type="submit"
            :disabled="loading"
            class="focus-ring w-full py-3 bg-gradient-to-r from-primary to-secondary text-primary-text text-sm font-bold rounded-full hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 shadow-lg shadow-primary/20 active:scale-[0.98]"
          >
            <span v-if="loading" class="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2 align-middle"></span>
            {{ mode === 'login' ? '登录' : '注册' }}
          </button>
        </form>

        <!-- 预设账号提示 -->
        <div class="mt-6 p-4 rounded-xl bg-card border border-subtle">
          <p class="text-xs text-text-muted mb-2">预设测试账号</p>
          <div class="text-xs text-text-secondary space-y-1.5">
            <p>管理员：<code class="text-primary bg-card px-1.5 py-0.5 rounded">admin</code></p>
            <p>学生：<code class="text-secondary bg-card px-1.5 py-0.5 rounded">student</code></p>
            <p class="text-xs text-text-muted mt-2">密码请联系管理员获取</p>
          </div>
        </div>
      </div>

      <!-- 返回首页 -->
      <div class="mt-8 text-center">
        <button
          type="button"
          class="min-h-11 px-3 text-xs text-text-muted hover:text-primary transition-colors duration-200 underline underline-offset-4"
          @click="$emit('go-home')"
        >
          返回首页
        </button>
      </div>

      <!-- Footer -->
      <p class="mt-4 text-center text-[11px] text-text-muted">
        EduAgent · 数据结构与算法智能学习工作台
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from "vue";
import { getCaptcha, login, register } from "../services/eduAgentApi";

const props = defineProps({
  screen: { type: String, default: "login" },
  initialAuthMode: { type: String, default: "login" },
  initialNotice: { type: String, default: "" },
  resetToken: { type: String, default: "" },
  verificationToken: { type: String, default: "" },
  submitLogin: { type: Function, default: null },
  submitRegister: { type: Function, default: null },
  submitForgot: { type: Function, default: null },
  submitReset: { type: Function, default: null },
  submitVerification: { type: Function, default: null },
});

const emit = defineEmits(["login-success", "go-home", "auth-mode-change"]);

const mode = ref(props.initialAuthMode === "register" ? "register" : "login");
const loading = ref(false);
const errorMsg = ref("");
const captchaSvg = ref("");
const captchaToken = ref("");

const form = reactive({
  userId: "",
  email: "",
  password: "",
  captchaAnswer: "",
});

function selectMode(nextMode) {
  mode.value = nextMode;
  errorMsg.value = "";
  emit("auth-mode-change", nextMode);
}

async function fetchCaptcha() {
  try {
    const data = await getCaptcha();
    captchaSvg.value = data.svg;
    captchaToken.value = data.captcha_token;
    form.captchaAnswer = "";
    errorMsg.value = "";
  } catch {
    errorMsg.value = "验证码加载失败，请检查网络连接";
  }
}

async function onSubmit() {
  errorMsg.value = "";
  if (!captchaToken.value) { errorMsg.value = "请先加载验证码"; return; }
  if (!form.captchaAnswer.trim()) { errorMsg.value = "请输入验证码答案"; return; }

  loading.value = true;
  try {
    let result;
    if (mode.value === "login") {
      result = typeof props.submitLogin === "function"
        ? await props.submitLogin(form.userId, form.password, captchaToken.value, form.captchaAnswer)
        : await login({
          user_id: form.userId,
          password: form.password,
          captcha_token: captchaToken.value,
          captcha_answer: form.captchaAnswer,
        });
    } else {
      if (!form.email.includes("@")) { errorMsg.value = "请输入有效的邮箱地址"; return; }
      result = typeof props.submitRegister === "function"
        ? await props.submitRegister(form.userId, form.email, form.password, captchaToken.value, form.captchaAnswer)
        : await register({
          user_id: form.userId,
          email: form.email,
          password: form.password,
          captcha_token: captchaToken.value,
          captcha_answer: form.captchaAnswer,
        });
    }
    emit("login-success", result);
  } catch (e) {
    const message = e?.response?.data?.detail || e?.message || "操作失败，请重试";
    await fetchCaptcha();
    errorMsg.value = message;
  } finally {
    loading.value = false;
  }
}

onMounted(fetchCaptcha);
</script>

<style scoped>
.auth-view {
  min-height: 100vh;
  min-height: 100dvh;
  padding-top: max(2rem, env(safe-area-inset-top, 0px));
  padding-bottom: max(2rem, env(safe-area-inset-bottom, 0px));
}

.captcha-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(7.5rem, 36vw, 8.75rem);
  gap: 0.75rem;
}

.captcha-preview :deep(svg) {
  width: 100%;
  height: 100%;
}

@media (max-width: 359px) {
  .captcha-row {
    grid-template-columns: minmax(0, 1fr) 7rem;
    gap: 0.5rem;
  }
}
</style>
