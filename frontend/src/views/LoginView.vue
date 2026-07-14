<template>
  <div class="min-h-screen bg-space-bg text-text-primary">
    <AuthView
      :screen="screen"
      :initial-auth-mode="initialAuthMode"
      :initial-notice="initialNotice"
      :reset-token="resetToken"
      :verification-token="verificationToken"
      :submit-login="onLogin"
      :submit-register="onRegister"
      :submit-forgot="onForgotPassword"
      :submit-reset="onResetPassword"
      :submit-verification="onVerifyEmail"
      @navigate="navigate"
      @auth-mode-change="setAuthMode"
      @verification-complete="finishVerification"
    />
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import AuthView from "../components/AuthView.vue";
import {
  requestPasswordReset,
  resetPassword,
  verifyEmail,
} from "../services/accountApi";
import { tokenStore } from "../services/apiClient";
import { markLoginSuccess, reportClientSessionStarted } from "../services/clientTelemetry";
import { useEduAgent } from "../composables/useEduAgent";

const route = useRoute();
const router = useRouter();
const { handleLogin, handleRegister, handleLogout } = useEduAgent();
const DEFAULT_REDIRECT = "/app";
const AUTH_ROUTE_NAMES = new Set([
  "login",
  "password-forgot",
  "password-reset",
  "email-verify",
]);

const screen = computed(() => (
  typeof route.query.reset_token === "string" ? "reset" : String(route.meta.authMode || "login")
));
const initialAuthMode = computed(() => route.query.mode === "register" ? "register" : "login");
const resetToken = computed(() => {
  if (typeof route.query.token === "string") return route.query.token;
  return typeof route.query.reset_token === "string" ? route.query.reset_token : "";
});
const verificationToken = computed(() => typeof route.query.token === "string" ? route.query.token : "");
const redirectTarget = computed(() => resolveRedirectTarget(route.query.redirect));
const initialNotice = computed(() => ({
  "account-deleted": "账户已注销，相关登录信息已从此设备移除。",
  "session-revoked": "此设备的会话已撤销，请重新登录。",
  "all-sessions-revoked": "所有设备会话已撤销，请重新登录。",
}[String(route.query.reason || "")] || ""));

async function onLogin(userId, password, captchaToken, captchaAnswer) {
  await handleLogin(userId, password, captchaToken, captchaAnswer);
  markLoginSuccess();
  void reportClientSessionStarted({ surface: "app" });
  await router.replace(redirectTarget.value);
}

async function onRegister(userId, email, password, captchaToken, captchaAnswer) {
  await handleRegister(userId, email, password, captchaToken, captchaAnswer);
  void reportClientSessionStarted({ surface: "app" });
  await router.replace(redirectTarget.value);
}

function onForgotPassword(email) {
  return requestPasswordReset(email);
}

async function onResetPassword(token, newPassword) {
  const payload = await resetPassword({ token, newPassword });
  handleLogout();
  return payload;
}

function onVerifyEmail(token) {
  return verifyEmail(token);
}

function navigate(target) {
  if (target && typeof target === "object" && target.target === "reset" && target.token) {
    router.push({ name: "password-reset", query: { token: target.token } });
    return;
  }
  const redirect = redirectTarget.value === DEFAULT_REDIRECT ? undefined : redirectTarget.value;
  const routeByTarget = {
    login: { name: "login", query: redirect ? { redirect } : {} },
    forgot: { name: "password-forgot", query: redirect ? { redirect } : {} },
  };
  router.push(routeByTarget[target] || { name: "landing" });
}

function setAuthMode(mode) {
  const query = { ...route.query };
  if (mode === "register") query.mode = "register";
  else delete query.mode;
  router.replace({ name: "login", query });
}

function finishVerification() {
  router.push(tokenStore.getAccessToken() ? { name: "account" } : { name: "login" });
}

function resolveRedirectTarget(candidate) {
  if (typeof candidate !== "string" || !candidate.startsWith("/") || candidate.startsWith("//")) {
    return DEFAULT_REDIRECT;
  }

  try {
    const resolved = router.resolve(candidate);
    const matchedAuthRoute = resolved.matched.some((record) => (
      AUTH_ROUTE_NAMES.has(String(record.name || ""))
      || typeof record.meta?.authMode === "string"
    ));
    const matchedFallbackRoute = resolved.matched.some((record) => Boolean(record.redirect));
    if (!resolved.matched.length || matchedAuthRoute || matchedFallbackRoute) {
      return DEFAULT_REDIRECT;
    }
    return resolved.fullPath;
  } catch {
    return DEFAULT_REDIRECT;
  }
}
</script>
