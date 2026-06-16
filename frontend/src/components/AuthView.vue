<template>
  <div class="flex items-center justify-center min-h-screen bg-gradient-to-br from-gray-900 via-gray-950 to-indigo-950">
    <div class="w-full max-w-md mx-4">
      <!-- Logo -->
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white text-2xl font-black mb-3">EA</div>
        <h1 class="text-2xl font-bold text-white">EduAgent</h1>
        <p class="text-gray-400 text-sm mt-1">个性化多智能体学习系统</p>
      </div>

      <!-- 卡片 -->
      <div class="bg-gray-900/80 backdrop-blur border border-gray-800 rounded-2xl p-6 shadow-2xl">
        <!-- 标签切换 -->
        <div class="flex mb-6 bg-gray-800/50 rounded-lg p-1">
          <button
            :class="mode === 'login' ? 'bg-gray-700 text-white shadow' : 'text-gray-400 hover:text-gray-200'"
            class="flex-1 py-2 text-sm font-medium rounded-md transition"
            @click="mode = 'login'"
          >登录</button>
          <button
            :class="mode === 'register' ? 'bg-gray-700 text-white shadow' : 'text-gray-400 hover:text-gray-200'"
            class="flex-1 py-2 text-sm font-medium rounded-md transition"
            @click="mode = 'register'"
          >注册</button>
        </div>

        <!-- 表单 -->
        <form @submit.prevent="onSubmit" class="space-y-4">
          <!-- 用户名 -->
          <div>
            <label class="block text-xs font-medium text-gray-400 mb-1">用户名</label>
            <input
              v-model="form.userId"
              type="text"
              required
              minlength="3"
              placeholder="请输入用户名"
              class="w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>

          <!-- 邮箱 (仅注册) -->
          <div v-if="mode === 'register'">
            <label class="block text-xs font-medium text-gray-400 mb-1">邮箱</label>
            <input
              v-model="form.email"
              type="email"
              required
              placeholder="请输入邮箱"
              class="w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>

          <!-- 密码 -->
          <div>
            <label class="block text-xs font-medium text-gray-400 mb-1">密码</label>
            <input
              v-model="form.password"
              type="password"
              required
              minlength="8"
              placeholder="至少 8 个字符"
              class="w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"
            />
          </div>

          <!-- 验证码 -->
          <div>
            <label class="block text-xs font-medium text-gray-400 mb-1">验证码</label>
            <div class="flex gap-2">
              <input
                v-model="form.captchaAnswer"
                type="text"
                required
                placeholder="计算结果"
                class="flex-1 px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:border-indigo-500 transition"
              />
              <div
                class="h-[42px] w-[140px] bg-gray-100 rounded-lg cursor-pointer overflow-hidden flex-shrink-0 border border-gray-700 hover:border-indigo-500 transition"
                v-html="captchaSvg"
                @click="fetchCaptcha"
                title="点击刷新验证码"
              ></div>
            </div>
          </div>

          <!-- 错误提示 -->
          <div v-if="errorMsg" class="text-red-400 text-xs bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2">{{ errorMsg }}</div>

          <!-- 提交按钮 -->
          <button
            type="submit"
            :disabled="loading"
            class="w-full py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-sm font-medium rounded-lg hover:from-indigo-500 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed transition shadow-lg"
          >
            <span v-if="loading" class="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2 align-middle"></span>
            {{ mode === 'login' ? '登录' : '注册' }}
          </button>
        </form>

        <!-- 预设账号提示 -->
        <div class="mt-6 p-3 bg-gray-800/40 rounded-lg border border-gray-800">
          <p class="text-xs text-gray-500 mb-2">预设测试账号</p>
          <div class="text-xs text-gray-400 space-y-1">
            <p>管理员：<code class="text-indigo-300 bg-gray-800 px-1 rounded">admin</code> / <code class="text-indigo-300 bg-gray-800 px-1 rounded">Admin@2026!</code></p>
            <p>学生：<code class="text-green-300 bg-gray-800 px-1 rounded">student</code> / <code class="text-green-300 bg-gray-800 px-1 rounded">Learn@2026</code></p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from "vue";
import { getCaptcha } from "../services/eduAgentApi";

const emit = defineEmits(["login", "register"]);

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
