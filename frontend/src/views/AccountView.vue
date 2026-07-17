<template>
  <AppPageFrame>
    <UserSettingsView
      :profile="profile"
      :settings="settings"
      :sessions="sessions"
      :current-session-id="currentSessionId"
      :loading="loading"
      :load-error="loadError"
      :actions="actions"
      :revoking-session-id="revokingSessionId"
      @back="router.push({ name: 'app-workspace' })"
      @retry-load="loadAccount"
      @save-profile="saveProfile"
      @save-settings="saveSettings"
      @request-verification="sendVerificationEmail"
      @retry-verification="retryEmailVerification"
      @revoke-session="revokeSession"
      @revoke-all-sessions="revokeAllSessions"
      @export-data="downloadDataExport"
      @delete-account="deleteAccount"
    />
  </AppPageFrame>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppPageFrame from "../components/AppPageFrame.vue";
import UserSettingsView from "../components/UserSettingsView.vue";
import {
  accountApiError,
  deleteUserAccount,
  exportUserData,
  getDeviceSessions,
  getUserProfile,
  getUserSettings,
  requestEmailVerification,
  revokeAllDeviceSessions,
  revokeDeviceSession,
  updateUserProfile,
  updateUserSettings,
  verifyEmail,
} from "../services/accountApi";
import { useEduAgent } from "../composables/useEduAgent";
import { useTheme } from "../composables/useTheme";

const route = useRoute();
const router = useRouter();
const { currentUser, handleLogout } = useEduAgent();
const { setTheme } = useTheme();
const WORKSPACE_PREFERENCES_KEY = "eduagent-workspace-preferences";

const defaultProfile = {
  user_id: "",
  display_name: "",
  email: "",
  university: "",
  major: "",
  grade: "",
  weekly_study_hours: 0,
  learning_goal: "",
  preferred_resource_style: "textual",
  preferred_pace: "steady",
  preferred_practice_intensity: "balanced",
  email_verified: false,
  email_verified_at: "",
  updated_at: "",
};

const defaultSettings = {
  preferences: {
    theme: "system",
    high_contrast: false,
    reduce_motion: false,
    font_size: 16,
  },
  privacy: {
    analytics_enabled: false,
    personalization_enabled: true,
    profile_visibility: "private",
  },
  email_verified: false,
  email_verified_at: "",
  updated_at: "",
};

const profile = ref({ ...defaultProfile });
const settings = ref({
  ...defaultSettings,
  preferences: { ...defaultSettings.preferences },
  privacy: { ...defaultSettings.privacy },
});
const sessions = ref([]);
const currentSessionId = ref("");
const loading = ref(true);
const loadError = ref("");
const revokingSessionId = ref("");
const pendingVerificationToken = ref("");

function actionState() {
  return { status: "idle", message: "" };
}

const actions = reactive({
  profile: actionState(),
  settings: actionState(),
  verification: actionState(),
  sessions: actionState(),
  export: actionState(),
  delete: actionState(),
});

function startAction(key) {
  actions[key].status = "loading";
  actions[key].message = "";
}

function finishAction(key, message) {
  actions[key].status = "success";
  actions[key].message = message;
}

function failAction(key, error, fallback) {
  actions[key].status = "error";
  actions[key].message = accountApiError(error, fallback);
}

function profileFromResponse(payload) {
  const source = payload?.profile || payload?.user || payload || {};
  return { ...defaultProfile, ...source };
}

function settingsFromResponse(payload) {
  const source = payload?.settings || payload || {};
  return {
    ...defaultSettings,
    ...source,
    preferences: { ...defaultSettings.preferences, ...(source.preferences || {}) },
    privacy: { ...defaultSettings.privacy, ...(source.privacy || {}) },
  };
}

function sessionsFromResponse(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.sessions)) return payload.sessions;
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
}

function applyInterfacePreferences(nextSettings) {
  const preferences = nextSettings?.preferences || {};
  const requestedTheme = preferences.theme || "system";
  const resolvedTheme = requestedTheme === "system"
    ? (window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark")
    : requestedTheme;
  setTheme(resolvedTheme);

  try {
    const existing = JSON.parse(window.localStorage.getItem(WORKSPACE_PREFERENCES_KEY) || "{}");
    window.localStorage.setItem(WORKSPACE_PREFERENCES_KEY, JSON.stringify({
      ...(existing && typeof existing === "object" && !Array.isArray(existing) ? existing : {}),
      highContrast: Boolean(preferences.high_contrast),
      reduceMotion: Boolean(preferences.reduce_motion),
      fontSize: Math.max(12, Math.min(24, Number(preferences.font_size) || 16)),
    }));
  } catch {
    // Server persistence still succeeds when browser storage is unavailable.
  }
}

async function loadAccount(force = false) {
  if (loading.value && !force) return;
  loading.value = true;
  loadError.value = "";
  try {
    const [profilePayload, settingsPayload, sessionPayload] = await Promise.all([
      getUserProfile(),
      getUserSettings(),
      getDeviceSessions(),
    ]);
    profile.value = profileFromResponse(profilePayload);
    settings.value = settingsFromResponse(settingsPayload);
    applyInterfacePreferences(settings.value);
    sessions.value = sessionsFromResponse(sessionPayload);
    currentSessionId.value = String(sessionPayload?.current_session_id || "");
    currentUser.value = { ...(currentUser.value || {}), ...profile.value };
  } catch (error) {
    loadError.value = accountApiError(error, "账户信息加载失败，请重试。");
  } finally {
    loading.value = false;
  }
}

async function saveProfile(nextProfile) {
  if (actions.profile.status === "loading") return;
  const emailWillChange = Object.prototype.hasOwnProperty.call(nextProfile || {}, "email")
    && String(nextProfile.email || "").trim().toLowerCase()
      !== String(profile.value.email || "").trim().toLowerCase();
  startAction("profile");
  try {
    const payload = await updateUserProfile(nextProfile);
    profile.value = profileFromResponse(payload);
    currentUser.value = { ...(currentUser.value || {}), ...profile.value };
    if (emailWillChange) {
      settings.value = {
        ...settings.value,
        email_verified: false,
        email_verified_at: "",
      };
      actions.verification.status = "idle";
      actions.verification.message = "";
      pendingVerificationToken.value = "";
    }
    finishAction("profile", "个人资料和学习偏好已保存。");
  } catch (error) {
    failAction("profile", error, "资料保存失败，请重试。");
  }
}

async function saveSettings(nextSettings) {
  if (actions.settings.status === "loading") return;
  startAction("settings");
  try {
    const payload = await updateUserSettings(nextSettings);
    settings.value = settingsFromResponse(payload);
    applyInterfacePreferences(settings.value);
    finishAction("settings", "界面偏好和隐私设置已保存。");
  } catch (error) {
    failAction("settings", error, "设置保存失败，请重试。");
  }
}

async function sendVerificationEmail() {
  if (actions.verification.status === "loading") return;
  startAction("verification");
  try {
    const payload = await requestEmailVerification();
    if (import.meta.env.DEV && typeof payload?.dev_token === "string" && payload.dev_token) {
      actions.verification.status = "idle";
      await consumeVerificationToken(payload.dev_token);
      return;
    }
    finishAction("verification", payload?.message || "验证邮件已发送，请在有效期内打开邮件中的链接。");
  } catch (error) {
    failAction("verification", error, "验证邮件发送失败，请重试。");
  }
}

async function clearVerificationQuery() {
  const query = { ...route.query };
  delete query.verify_token;
  await router.replace({ name: "account", query, hash: route.hash });
}

async function consumeVerificationToken(token) {
  const normalizedToken = String(token || "").trim();
  if (!normalizedToken || actions.verification.status === "loading") return;
  pendingVerificationToken.value = normalizedToken;
  startAction("verification");
  if (typeof route.query.verify_token === "string") {
    try {
      await clearVerificationQuery();
    } catch {
      // Verification can proceed even if browser history could not be replaced.
    }
  }
  try {
    const verificationPayload = await verifyEmail(normalizedToken);
    pendingVerificationToken.value = "";
    if (
      verificationPayload?.user_id
      && profile.value.user_id
      && String(verificationPayload.user_id) !== String(profile.value.user_id)
    ) {
      finishAction("verification", "验证链接属于另一个账户。对应邮箱已验证，请切换到该账户查看。");
      return;
    }
    if (verificationPayload?.email_verified !== true) {
      profile.value = { ...profile.value, email_verified: false, email_verified_at: "" };
      settings.value = { ...settings.value, email_verified: false, email_verified_at: "" };
      finishAction("verification", "邮箱地址已发生变化，请为当前邮箱重新发送验证邮件。");
      return;
    }
    profile.value = {
      ...profile.value,
      email_verified: true,
      email_verified_at: verificationPayload?.email_verified_at || profile.value.email_verified_at,
    };
    settings.value = {
      ...settings.value,
      email_verified: true,
      email_verified_at: verificationPayload?.email_verified_at || settings.value.email_verified_at,
    };
    try {
      const [profilePayload, settingsPayload] = await Promise.all([
        getUserProfile(),
        getUserSettings(),
      ]);
      profile.value = profileFromResponse(profilePayload);
      settings.value = settingsFromResponse(settingsPayload);
      applyInterfacePreferences(settings.value);
      currentUser.value = { ...(currentUser.value || {}), ...profile.value };
      finishAction("verification", "邮箱验证成功，账户安全信息已更新。");
    } catch {
      finishAction("verification", "邮箱已验证，但最新状态暂时无法刷新。重新打开账户页即可同步。");
    }
  } catch (error) {
    failAction("verification", error, "邮箱验证失败，链接可能已过期。你可以重试或重新发送验证邮件。");
  }
}

function retryEmailVerification() {
  if (pendingVerificationToken.value) {
    consumeVerificationToken(pendingVerificationToken.value);
    return;
  }
  sendVerificationEmail();
}

function sessionIdOf(session) {
  return String(session?.session_id || session?.id || "");
}

async function revokeSession(session) {
  const sessionId = sessionIdOf(session);
  if (!sessionId || revokingSessionId.value) return;
  revokingSessionId.value = sessionId;
  actions.sessions.status = "loading";
  actions.sessions.message = "";
  try {
    const payload = await revokeDeviceSession(sessionId);
    const revokedCurrent = payload?.current_session_revoked === true
      || sessionId === currentSessionId.value
      || session?.is_current === true
      || session?.current === true;
    if (revokedCurrent) {
      handleLogout();
      await router.replace({ name: "login", query: { reason: "session-revoked" } });
      return;
    }
    sessions.value = sessions.value.filter((item) => sessionIdOf(item) !== sessionId);
    finishAction("sessions", "该设备会话已撤销。");
  } catch (error) {
    failAction("sessions", error, "设备会话撤销失败，请重试。");
  } finally {
    revokingSessionId.value = "";
  }
}

async function revokeAllSessions() {
  if (actions.sessions.status === "loading") return;
  startAction("sessions");
  try {
    await revokeAllDeviceSessions();
    handleLogout();
    await router.replace({ name: "login", query: { reason: "all-sessions-revoked" } });
  } catch (error) {
    failAction("sessions", error, "无法撤销全部设备会话，请重试。");
  }
}

async function downloadDataExport() {
  if (actions.export.status === "loading") return;
  startAction("export");
  try {
    const { blob, filename } = await exportUserData();
    const objectUrl = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.hidden = true;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
    finishAction("export", "数据导出已开始下载。");
  } catch (error) {
    failAction("export", error, "数据导出失败，请重试。");
  }
}

async function deleteAccount(payload) {
  if (actions.delete.status === "loading") return;
  startAction("delete");
  try {
    await deleteUserAccount(payload);
    handleLogout();
    await router.replace({ name: "login", query: { reason: "account-deleted" } });
  } catch (error) {
    failAction("delete", error, "账户注销失败，请核对密码后重试。");
  }
}

onMounted(async () => {
  const verificationToken = typeof route.query.verify_token === "string" ? route.query.verify_token : "";
  if (verificationToken) {
    pendingVerificationToken.value = verificationToken;
    try {
      await clearVerificationQuery();
    } catch {
      // The token remains in memory so verification can still proceed.
    }
  }
  await loadAccount(true);
  if (verificationToken) await consumeVerificationToken(verificationToken);
});
</script>
