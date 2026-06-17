<template>
  <div class="relative z-10 flex min-h-screen items-center justify-center px-4 py-12 animate-fadeIn">
    <div class="w-full max-w-md">
      <!-- Logo -->
      <div class="text-center mb-10">
        <div class="relative inline-flex items-center justify-center w-20 h-20 rounded-[22px] mb-5 overflow-hidden shadow-glow">
          <div class="absolute inset-0 bg-gradient-to-br from-primary to-secondary opacity-90" />
          <div class="absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.25),transparent)]" />
          <span class="relative text-white text-2xl font-black">EA</span>
        </div>
        <h1 class="text-3xl font-black tracking-tight text-text-primary mb-2">EduAgent</h1>
        <p class="text-sm text-text-secondary">个性化多智能体学习系统</p>
      </div>

      <!-- 卡片 -->
      <div class="glass-card rounded-[28px] p-7">
        <!-- 标签切换 -->
        <div class="flex mb-7 p-1 rounded-xl bg-card border border-subtle">
          <button
            :class="mode === 'login' ? 'bg-card-hover text-text-primary shadow-lg shadow-black/20' : 'text-text-muted hover:text-text-secondary'"
            class="flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200"
            @click="mode = 'login'"
          >登录</button>
          <button
            :class="mode === 'register' ? 'bg-card-hover text-text-primary shadow-lg shadow-black/20' : 'text-text-muted hover:text-text-secondary'"
            class="flex-1 py-2.5 text-sm font-medium rounded-lg transition-all duration-200"
            @click="mode = 'register'"
          >注册</button>
        </div>

        <!-- 表单 -->
        <form @submit.prevent="onSubmit" class="space-y-5">
          <!-- 用户名 -->
          <div>
            <label class="block text-xs font-semibold text-text-secondary mb-1.5">用户名</label>
            <input
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
            <label class="block text-xs font-semibold text-text-secondary mb-1.5">邮箱</label>
            <input
              v-model="form.email"
              type="email"
              required
              placeholder="请输入邮箱"
              class="w-full px-4 py-3 bg-input border border-subtle rounded-xl text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20 transition"
            />
          </div>

          <!-- 密码 -->
          <div>
            <label class="block text-xs font-semibold text-text-secondary mb-1.5">密码</label>
            <input
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
            <label class="block text-xs font-semibold text-text-secondary mb-1.5">验证码</label>
            <div class="flex gap-3">
              <input
                v-model="form.captchaAnswer"
                type="text"
                required
                placeholder="计算结果"
                class="flex-1 px-4 py-3 bg-input border border-subtle rounded-xl text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/20 transition"
              />
              <div
                class="h-[46px] w-[140px] bg-space-surface rounded-xl cursor-pointer overflow-hidden flex-shrink-0 border border-subtle hover:border-primary/40 transition"
                v-html="captchaSvg"
                @click="fetchCaptcha"
                title="点击刷新验证码"
              ></div>
            </div>
          </div>

          <!-- 错误提示 -->
          <div v-if="errorMsg" class="rounded-xl border border-error/20 bg-error-soft px-3 py-2.5 text-xs text-error">{{ errorMsg }}</div>

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
            <p>管理员：<code class="text-primary bg-card px-1.5 py-0.5 rounded">admin</code> / <code class="text-primary bg-card px-1.5 py-0.5 rounded">Admin@2026!</code></p>
            <p>学生：<code class="text-secondary bg-card px-1.5 py-0.5 rounded">student</code> / <code class="text-secondary bg-card px-1.5 py-0.5 rounded">Learn@2026</code></p>
          </div>
        </div>
      </div>

      <!-- 返回首页 -->
      <div class="mt-8 text-center">
        <button
          type="button"
          class="text-xs text-text-muted hover:text-primary transition-colors duration-200 underline underline-offset-4"
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
import { getCaptcha } from "../services/eduAgentApi";

const emit = defineEmits(["login", "register", "go-home"]);

const mode = ref("login");
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
    if (mode.value === "login") {
      emit("login", form.userId, form.password, captchaToken.value, form.captchaAnswer);
    } else {
      if (!form.email.includes("@")) { errorMsg.value = "请输入有效的邮箱地址"; loading.value = false; return; }
      emit("register", form.userId, form.email, form.password, captchaToken.value, form.captchaAnswer);
    }
  } catch (e) {
    errorMsg.value = e?.response?.data?.detail || "操作失败，请重试";
  }
  loading.value = false;
}

onMounted(fetchCaptcha);
</script>
