<template>
  <main class="auth-page relative z-10 flex min-h-screen items-center justify-center px-4 py-8 sm:py-12">
    <div class="w-full max-w-[440px]">
      <RouterLink
        :to="{ name: 'landing' }"
        class="focus-ring mx-auto mb-7 flex min-h-11 w-fit items-center gap-3 rounded-lg px-2 text-text-primary"
        aria-label="返回 EduAgent 首页"
      >
        <span class="flex h-11 w-11 items-center justify-center rounded-lg bg-primary-soft text-sm font-black text-primary">EA</span>
        <span>
          <strong class="block text-lg leading-5">EduAgent</strong>
          <span class="mt-1 block text-xs text-text-muted">自适应学习工作台</span>
        </span>
      </RouterLink>

      <section class="auth-panel rounded-xl bg-space-panel px-5 py-6 sm:px-7 sm:py-7" :aria-busy="loading">
        <header>
          <h1 class="text-2xl font-black text-text-primary">{{ title }}</h1>
          <p class="mt-2 text-sm leading-6 text-text-secondary">{{ description }}</p>
        </header>

        <p
          v-if="initialNotice"
          class="mt-5 rounded-lg bg-success-soft px-4 py-3 text-sm text-success"
          role="status"
        >
          {{ initialNotice }}
        </p>

        <div v-if="screen === 'login'" class="mt-6">
          <div class="grid grid-cols-2 rounded-lg bg-space-elevated p-1" role="tablist" aria-label="账户操作">
            <button
              v-for="item in authModes"
              :id="`auth-tab-${item.value}`"
              :key="item.value"
              type="button"
              role="tab"
              class="focus-ring min-h-11 rounded-md px-3 text-sm font-semibold transition-colors"
              :class="accountMode === item.value ? 'bg-space-panel text-text-primary shadow-sm' : 'text-text-muted hover:text-text-primary'"
              :aria-selected="accountMode === item.value"
              :disabled="loading"
              @click="selectAccountMode(item.value)"
            >
              {{ item.label }}
            </button>
          </div>

          <form class="mt-6 space-y-5" @submit.prevent="submitCredentials">
            <div>
              <label for="auth-user-id" class="auth-label">用户名</label>
              <input
                id="auth-user-id"
                v-model.trim="credentialForm.userId"
                class="auth-input focus-ring"
                type="text"
                autocomplete="username"
                minlength="3"
                maxlength="32"
                required
                placeholder="请输入用户名"
              />
            </div>

            <div v-if="accountMode === 'register'">
              <label for="auth-email" class="auth-label">邮箱</label>
              <input
                id="auth-email"
                v-model.trim="credentialForm.email"
                class="auth-input focus-ring"
                type="email"
                autocomplete="email"
                required
                placeholder="name@example.com"
              />
            </div>

            <div>
              <div class="mb-2 flex items-center justify-between gap-3">
                <label for="auth-password" class="text-sm font-semibold text-text-secondary">密码</label>
                <button
                  v-if="accountMode === 'login'"
                  type="button"
                  class="focus-ring min-h-11 rounded-md px-2 text-sm font-semibold text-primary hover:text-primary-dark"
                  @click="$emit('navigate', 'forgot')"
                >
                  忘记密码
                </button>
              </div>
              <div class="relative">
                <input
                  id="auth-password"
                  v-model="credentialForm.password"
                  class="auth-input focus-ring pr-16"
                  :type="showPassword ? 'text' : 'password'"
                  :autocomplete="accountMode === 'login' ? 'current-password' : 'new-password'"
                  minlength="8"
                  required
                  placeholder="至少 8 个字符"
                />
                <button
                  type="button"
                  class="focus-ring absolute right-1 top-1/2 min-h-11 -translate-y-1/2 rounded-md px-3 text-xs font-semibold text-text-secondary"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  @click="showPassword = !showPassword"
                >
                  {{ showPassword ? "隐藏" : "显示" }}
                </button>
              </div>
            </div>

            <div>
              <div class="mb-2 flex items-center justify-between gap-3">
                <label for="auth-captcha" class="text-sm font-semibold text-text-secondary">验证码</label>
                <button
                  type="button"
                  class="focus-ring min-h-11 rounded-md px-2 text-sm font-semibold text-primary"
                  :disabled="captchaLoading"
                  @click="fetchCaptcha()"
                >
                  {{ captchaLoading ? "刷新中" : "换一题" }}
                </button>
              </div>
              <div class="grid grid-cols-[minmax(0,1fr)_132px] gap-3">
                <input
                  id="auth-captcha"
                  v-model.trim="credentialForm.captchaAnswer"
                  class="auth-input focus-ring"
                  type="text"
                  inputmode="numeric"
                  autocomplete="off"
                  required
                  placeholder="计算结果"
                />
                <button
                  type="button"
                  class="captcha-box focus-ring flex min-h-11 items-center justify-center overflow-hidden rounded-lg bg-space-elevated px-2"
                  :disabled="captchaLoading"
                  aria-label="刷新验证码"
                  title="点击刷新验证码"
                  @click="fetchCaptcha()"
                >
                  <span v-if="captchaLoading" class="text-xs text-text-muted">正在加载</span>
                  <span v-else-if="captchaSvg" class="captcha-svg" aria-hidden="true" v-html="captchaSvg" />
                  <span v-else class="text-xs font-semibold text-error">加载失败</span>
                </button>
              </div>
            </div>

            <AuthFeedback :error="errorMsg" :loading="loading" :retryable="Boolean(lastAction)" @retry="retryLastAction" />

            <button type="submit" class="auth-primary focus-ring" :disabled="loading || captchaLoading">
              <span v-if="loading" class="auth-spinner" aria-hidden="true" />
              {{ loading ? "正在处理" : accountMode === "login" ? "登录" : "创建账户" }}
            </button>
          </form>

          <div v-if="showTestAccounts" class="mt-5 rounded-lg bg-space-elevated px-4 py-3 text-xs leading-6 text-text-secondary">
            <strong class="text-text-primary">开发测试账户</strong>
            <p>可使用本地开发配置中的 admin 或 student 账户。</p>
          </div>
        </div>

        <form v-else-if="screen === 'forgot' && !successMsg" class="mt-6 space-y-5" @submit.prevent="submitForgotPassword">
          <div>
            <label for="forgot-email" class="auth-label">注册邮箱</label>
            <input
              id="forgot-email"
              v-model.trim="recoveryForm.email"
              class="auth-input focus-ring"
              type="email"
              autocomplete="email"
              required
              placeholder="name@example.com"
            />
          </div>
          <AuthFeedback :error="errorMsg" :loading="loading" :retryable="Boolean(lastAction)" @retry="retryLastAction" />
          <button type="submit" class="auth-primary focus-ring" :disabled="loading">
            <span v-if="loading" class="auth-spinner" aria-hidden="true" />
            {{ loading ? "正在发送" : "发送重置邮件" }}
          </button>
        </form>

        <form v-else-if="screen === 'reset' && !successMsg" class="mt-6 space-y-5" @submit.prevent="submitPasswordReset">
          <div v-if="!resetToken">
            <label for="reset-token" class="auth-label">重置令牌</label>
            <input id="reset-token" v-model.trim="recoveryForm.token" class="auth-input focus-ring" type="text" autocomplete="one-time-code" required />
          </div>
          <div>
            <label for="reset-password" class="auth-label">新密码</label>
            <input id="reset-password" v-model="recoveryForm.newPassword" class="auth-input focus-ring" type="password" autocomplete="new-password" minlength="8" maxlength="128" required placeholder="8 至 128 个字符" />
          </div>
          <div>
            <label for="reset-password-confirm" class="auth-label">确认新密码</label>
            <input id="reset-password-confirm" v-model="recoveryForm.confirmPassword" class="auth-input focus-ring" type="password" autocomplete="new-password" minlength="8" maxlength="128" required placeholder="再次输入新密码" />
          </div>
          <AuthFeedback :error="errorMsg" :loading="loading" :retryable="Boolean(lastAction)" @retry="retryLastAction" />
          <button type="submit" class="auth-primary focus-ring" :disabled="loading">
            <span v-if="loading" class="auth-spinner" aria-hidden="true" />
            {{ loading ? "正在重置" : "重置密码" }}
          </button>
        </form>

        <form v-else-if="screen === 'verify' && !successMsg" class="mt-6 space-y-5" @submit.prevent="submitEmailVerification">
          <div v-if="!verificationToken">
            <label for="verification-token" class="auth-label">邮箱验证令牌</label>
            <input id="verification-token" v-model.trim="recoveryForm.verificationToken" class="auth-input focus-ring" type="text" autocomplete="one-time-code" required />
          </div>
          <AuthFeedback :error="errorMsg" :loading="loading" :retryable="Boolean(lastAction)" @retry="retryLastAction" />
          <button type="submit" class="auth-primary focus-ring" :disabled="loading">
            <span v-if="loading" class="auth-spinner" aria-hidden="true" />
            {{ loading ? "正在验证" : "验证邮箱" }}
          </button>
        </form>

        <div v-else-if="successMsg" class="mt-6" role="status">
          <div class="rounded-lg bg-success-soft px-4 py-4 text-sm leading-6 text-success">
            <strong class="block text-base">操作已完成</strong>
            <p class="mt-1">{{ successMsg }}</p>
          </div>
          <button type="button" class="auth-primary focus-ring mt-5" @click="finishSuccess">
            {{ screen === "verify" ? "继续使用 EduAgent" : "返回登录" }}
          </button>
        </div>

        <button
          v-if="screen !== 'login' && !successMsg"
          type="button"
          class="focus-ring mt-6 min-h-11 w-full rounded-lg text-sm font-semibold text-text-secondary hover:bg-space-elevated hover:text-text-primary"
          @click="$emit('navigate', 'login')"
        >
          返回登录
        </button>
      </section>

      <p class="mt-5 text-center text-xs leading-5 text-text-muted">EduAgent 不会通过邮件索要你的密码。</p>
    </div>
  </main>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, reactive, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import DOMPurify from "dompurify";
import { accountApiError } from "../services/accountApi";
import { getCaptcha } from "../services/eduAgentApi";

const props = defineProps({
  screen: { type: String, default: "login" },
  initialAuthMode: { type: String, default: "login" },
  initialNotice: { type: String, default: "" },
  resetToken: { type: String, default: "" },
  verificationToken: { type: String, default: "" },
  submitLogin: { type: Function, required: true },
  submitRegister: { type: Function, required: true },
  submitForgot: { type: Function, required: true },
  submitReset: { type: Function, required: true },
  submitVerification: { type: Function, required: true },
});

const emit = defineEmits(["navigate", "auth-mode-change", "verification-complete"]);

const AuthFeedback = defineComponent({
  props: {
    error: { type: String, default: "" },
    loading: { type: Boolean, default: false },
    retryable: { type: Boolean, default: false },
  },
  emits: ["retry"],
  setup(feedbackProps, { emit: feedbackEmit }) {
    return () => feedbackProps.error
      ? h("div", { class: "flex items-center justify-between gap-3 rounded-lg bg-error-soft px-4 py-3 text-sm text-error", role: "alert" }, [
        h("span", { class: "min-w-0 break-words leading-5" }, feedbackProps.error),
        feedbackProps.retryable ? h("button", {
          type: "button",
          class: "focus-ring min-h-11 shrink-0 rounded-md px-3 font-semibold",
          disabled: feedbackProps.loading,
          onClick: () => feedbackEmit("retry"),
        }, "重试") : null,
      ])
      : null;
  },
});

const authModes = [
  { value: "login", label: "登录" },
  { value: "register", label: "注册" },
];
const accountMode = ref(props.initialAuthMode === "register" ? "register" : "login");
const loading = ref(false);
const captchaLoading = ref(false);
const captchaSvg = ref("");
const captchaToken = ref("");
const errorMsg = ref("");
const successMsg = ref("");
const showPassword = ref(false);
const lastAction = ref(null);

const credentialForm = reactive({ userId: "", email: "", password: "", captchaAnswer: "" });
const recoveryForm = reactive({ email: "", token: "", newPassword: "", confirmPassword: "", verificationToken: "" });

const title = computed(() => ({
  login: accountMode.value === "register" ? "创建学习账户" : "欢迎回来",
  forgot: "找回密码",
  reset: "设置新密码",
  verify: "验证邮箱",
}[props.screen] || "账户验证"));

const description = computed(() => ({
  login: accountMode.value === "register" ? "注册后即可保存课程进度和学习记录。" : "登录后继续上一次学习任务。",
  forgot: "输入注册邮箱。若账户存在，我们会发送一次性重置链接。",
  reset: "新密码至少 8 个字符，设置成功后请重新登录。",
  verify: "确认邮箱归属，以便接收重要的账户安全通知。",
}[props.screen] || ""));

const showTestAccounts = computed(() => (
  import.meta.env.DEV && import.meta.env.VITE_SHOW_TEST_ACCOUNTS === "true"
));

function selectAccountMode(nextMode) {
  if (nextMode === accountMode.value || loading.value) return;
  accountMode.value = nextMode;
  errorMsg.value = "";
  credentialForm.password = "";
  emit("auth-mode-change", nextMode);
  fetchCaptcha();
}

async function fetchCaptcha({ preserveError = false } = {}) {
  if (captchaLoading.value) return;
  const previousError = errorMsg.value;
  captchaLoading.value = true;
  if (!preserveError) errorMsg.value = "";
  try {
    const data = await getCaptcha();
    captchaSvg.value = DOMPurify.sanitize(String(data?.svg || ""), {
      USE_PROFILES: { svg: true, svgFilters: true },
    });
    captchaToken.value = String(data?.captcha_token || "");
    credentialForm.captchaAnswer = "";
    if (!captchaToken.value) throw new Error("验证码响应无效");
  } catch (error) {
    captchaSvg.value = "";
    captchaToken.value = "";
    errorMsg.value = accountApiError(error, "验证码加载失败，请重试。");
    lastAction.value = () => fetchCaptcha();
  } finally {
    captchaLoading.value = false;
    if (preserveError && captchaToken.value) errorMsg.value = previousError;
  }
}

async function runAction(action, fallback) {
  if (loading.value) return;
  errorMsg.value = "";
  loading.value = true;
  try {
    await action();
  } catch (error) {
    errorMsg.value = accountApiError(error, fallback);
    throw error;
  } finally {
    loading.value = false;
  }
}

async function submitCredentials() {
  lastAction.value = () => submitCredentials();
  if (!captchaToken.value) {
    errorMsg.value = "验证码尚未加载，请先刷新验证码。";
    lastAction.value = () => fetchCaptcha();
    return;
  }

  const action = async () => {
    if (accountMode.value === "login") {
      await props.submitLogin(credentialForm.userId, credentialForm.password, captchaToken.value, credentialForm.captchaAnswer);
    } else {
      await props.submitRegister(credentialForm.userId, credentialForm.email, credentialForm.password, captchaToken.value, credentialForm.captchaAnswer);
    }
  };

  try {
    await runAction(action, accountMode.value === "login" ? "登录失败，请重试。" : "注册失败，请重试。");
  } catch {
    await fetchCaptcha({ preserveError: true });
  }
}

async function submitForgotPassword() {
  lastAction.value = () => submitForgotPassword();
  const action = async () => {
    const payload = await props.submitForgot(recoveryForm.email);
    if (import.meta.env.DEV && typeof payload?.dev_token === "string" && payload.dev_token) {
      emit("navigate", { target: "reset", token: payload.dev_token });
      return;
    }
    successMsg.value = "如果该邮箱已注册，重置链接会在几分钟内送达。请同时检查垃圾邮件。";
  };
  try {
    await runAction(action, "暂时无法发送重置邮件，请稍后重试。");
  } catch {
    // The error is rendered next to the form and can be retried in place.
  }
}

async function submitPasswordReset() {
  lastAction.value = () => submitPasswordReset();
  if (recoveryForm.newPassword !== recoveryForm.confirmPassword) {
    errorMsg.value = "两次输入的密码不一致。";
    lastAction.value = () => submitPasswordReset();
    return;
  }
  const token = props.resetToken || recoveryForm.token;
  if (!token) {
    errorMsg.value = "重置链接缺少有效令牌。";
    return;
  }

  const action = async () => {
    await props.submitReset(token, recoveryForm.newPassword);
    successMsg.value = "密码已更新。现在可以使用新密码登录。";
  };
  try {
    await runAction(action, "密码重置失败，链接可能已失效，请重新申请。");
  } catch {
    // The error is rendered next to the form and can be retried in place.
  }
}

async function submitEmailVerification() {
  lastAction.value = () => submitEmailVerification();
  const token = props.verificationToken || recoveryForm.verificationToken;
  if (!token) {
    errorMsg.value = "验证链接缺少有效令牌。";
    return;
  }

  const action = async () => {
    await props.submitVerification(token);
    successMsg.value = "邮箱验证成功，账户安全信息已更新。";
  };
  try {
    await runAction(action, "邮箱验证失败，链接可能已过期。");
  } catch {
    // The error is rendered next to the form and can be retried in place.
  }
}

function retryLastAction() {
  if (!loading.value && typeof lastAction.value === "function") {
    lastAction.value();
  }
}

function finishSuccess() {
  if (props.screen === "verify") {
    emit("verification-complete");
    return;
  }
  emit("navigate", "login");
}

watch(
  () => props.initialAuthMode,
  (next) => {
    accountMode.value = next === "register" ? "register" : "login";
  },
);

watch(
  () => props.screen,
  (next) => {
    errorMsg.value = "";
    successMsg.value = "";
    lastAction.value = null;
    if (next === "login" && !captchaToken.value) fetchCaptcha();
  },
);

onMounted(() => {
  if (props.screen === "login") fetchCaptcha();
});
</script>

<style scoped>
.auth-panel {
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-md);
}

.auth-label {
  display: block;
  margin-bottom: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 600;
}

.auth-input {
  min-height: 2.75rem;
  width: 100%;
  border: 1px solid var(--border-subtle);
  border-radius: 0.5rem;
  background: var(--input-bg);
  padding: 0.7rem 0.875rem;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.auth-input::placeholder {
  color: var(--text-muted);
}

.auth-input:hover {
  border-color: var(--border-hover);
}

.auth-primary {
  display: inline-flex;
  min-height: 2.75rem;
  width: 100%;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  border-radius: 0.5rem;
  background: var(--color-primary);
  padding: 0.7rem 1rem;
  color: var(--color-primary-text);
  font-size: 0.875rem;
  font-weight: 700;
  transition: background-color 160ms ease-out, transform 160ms ease-out;
}

.auth-primary:hover:not(:disabled) {
  background: var(--color-primary-dark);
}

.auth-primary:active:not(:disabled) {
  transform: scale(0.99);
}

.auth-primary:disabled,
.captcha-box:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.captcha-box {
  border: 1px solid var(--border-subtle);
}

.captcha-svg :deep(svg) {
  display: block;
  max-height: 2.5rem;
  max-width: 7rem;
}

.auth-spinner {
  width: 1rem;
  height: 1rem;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 9999px;
  animation: auth-spin 700ms linear infinite;
}

@keyframes auth-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 380px) {
  .auth-panel {
    padding-inline: 1rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .auth-spinner {
    animation-duration: 1.4s;
  }
}
</style>
