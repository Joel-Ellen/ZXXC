<template>
  <section class="relative z-10 px-4 py-6 sm:px-6 lg:px-8">
    <div class="mx-auto w-full max-w-6xl">
      <header class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p class="text-sm font-semibold text-primary">账户与安全</p>
          <h1 class="mt-1 text-2xl font-black text-text-primary sm:text-3xl">管理你的 EduAgent 账户</h1>
          <p class="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">资料会参与学习路径个性化；安全与隐私设置会同步到所有设备。</p>
        </div>
        <button type="button" class="account-secondary focus-ring shrink-0" @click="$emit('back')">返回学习</button>
      </header>

      <div v-if="loading" class="account-main rounded-xl bg-space-panel p-5 sm:p-7" aria-busy="true" aria-label="正在加载账户信息">
        <div class="space-y-4">
          <div class="skeleton-line h-6 w-36 rounded" />
          <div class="skeleton-line h-11 w-full rounded-lg" />
          <div class="skeleton-line h-11 w-full rounded-lg" />
          <div class="skeleton-line h-28 w-full rounded-lg" />
        </div>
      </div>

      <div v-else-if="loadError" class="account-main rounded-xl bg-space-panel px-5 py-10 text-center sm:px-7" role="alert">
        <h2 class="text-lg font-black text-text-primary">账户信息未能加载</h2>
        <p class="mx-auto mt-2 max-w-lg text-sm leading-6 text-error">{{ loadError }}</p>
        <button type="button" class="account-primary focus-ring mt-5" @click="$emit('retry-load')">重新加载</button>
      </div>

      <div v-else class="account-layout">
        <nav class="account-nav" aria-label="账户设置目录">
          <a v-for="item in navigation" :key="item.id" :href="`#${item.id}`" class="focus-ring">{{ item.label }}</a>
        </nav>

        <main class="account-main overflow-hidden rounded-xl bg-space-panel">
          <form id="profile" class="account-section" @submit.prevent="saveProfile('profile')">
            <div class="section-heading">
              <div>
                <h2>个人资料</h2>
                <p>用于课程问卷、学习报告和 Tutor 称呼。</p>
              </div>
              <span class="rounded-full bg-space-elevated px-3 py-1.5 text-xs font-semibold text-text-secondary">{{ profile.user_id }}</span>
            </div>

            <div class="mt-6 grid gap-5 sm:grid-cols-2">
              <div>
                <label for="account-display-name" class="account-label">显示名称</label>
                <input id="account-display-name" v-model.trim="profileDraft.display_name" class="account-input focus-ring" type="text" maxlength="128" autocomplete="name" />
              </div>
              <div>
                <label for="account-email" class="account-label">邮箱</label>
                <input id="account-email" v-model.trim="profileDraft.email" class="account-input focus-ring" type="email" maxlength="256" autocomplete="email" required />
              </div>
              <div v-if="emailChanged" class="sm:col-span-2">
                <label for="account-email-password" class="account-label">当前密码</label>
                <input
                  id="account-email-password"
                  v-model="emailPassword"
                  class="account-input focus-ring"
                  type="password"
                  maxlength="128"
                  autocomplete="current-password"
                  required
                  aria-describedby="account-email-password-help"
                />
                <p id="account-email-password-help" class="mt-2 text-xs leading-5 text-text-muted">
                  更换用于登录和找回密码的邮箱前，需要重新验证身份。
                </p>
              </div>
              <div>
                <label for="account-university" class="account-label">学校</label>
                <input id="account-university" v-model.trim="profileDraft.university" class="account-input focus-ring" type="text" maxlength="256" autocomplete="organization" />
              </div>
              <div>
                <label for="account-major" class="account-label">专业</label>
                <input id="account-major" v-model.trim="profileDraft.major" class="account-input focus-ring" type="text" maxlength="256" />
              </div>
              <div>
                <label for="account-grade" class="account-label">年级</label>
                <input id="account-grade" v-model.trim="profileDraft.grade" class="account-input focus-ring" type="text" maxlength="64" />
              </div>
              <div>
                <label for="account-weekly-hours" class="account-label">每周学习目标（小时）</label>
                <input id="account-weekly-hours" v-model.number="profileDraft.weekly_study_hours" class="account-input focus-ring" type="number" min="0" max="168" step="1" inputmode="numeric" />
              </div>
            </div>

            <div class="mt-5 flex flex-col gap-3 rounded-lg bg-space-elevated px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p class="text-sm font-bold text-text-primary">邮箱状态</p>
                <p class="mt-1 text-sm leading-5" :class="emailChanged ? 'text-warning' : emailVerified ? 'text-success' : 'text-text-secondary'">
                  {{ emailChanged ? "新邮箱保存后需要重新验证。" : emailVerified ? `已验证${verifiedAt ? ` · ${formatDate(verifiedAt)}` : ""}` : "尚未验证，部分安全通知可能无法送达。" }}
                </p>
              </div>
              <button
                v-if="!emailVerified || emailChanged"
                type="button"
                class="account-secondary focus-ring shrink-0"
                :disabled="actions.verification.status === 'loading' || emailChanged"
                :title="emailChanged ? '请先保存新的邮箱地址' : ''"
                @click="$emit('request-verification')"
              >
                {{ actions.verification.status === "loading" ? "正在发送" : emailChanged ? "请先保存邮箱" : "发送验证邮件" }}
              </button>
            </div>
            <ActionFeedback :action="actions.verification" @retry="$emit('retry-verification')" />

            <div class="section-actions">
              <ActionFeedback v-if="profileFeedbackSection === 'profile'" :action="actions.profile" @retry="saveProfile('profile')" />
              <button
                type="submit"
                class="account-primary focus-ring"
                :disabled="actions.profile.status === 'loading' || (emailChanged && !emailPassword)"
              >
                {{ actions.profile.status === "loading" && profileFeedbackSection === "profile" ? "正在保存" : "保存个人资料" }}
              </button>
            </div>
          </form>

          <form id="learning" class="account-section" @submit.prevent="saveProfile('learning')">
            <div class="section-heading">
              <div>
                <h2>学习目标与偏好</h2>
                <p>这些信息会影响新课程的资源形式、节奏和练习密度。</p>
              </div>
            </div>

            <div class="mt-6">
              <label for="account-learning-goal" class="account-label">当前学习目标</label>
              <textarea id="account-learning-goal" v-model.trim="profileDraft.learning_goal" class="account-input focus-ring min-h-28 resize-y" maxlength="1000" placeholder="例如：在八周内掌握常见数据结构，并能独立完成中等难度算法题。" />
            </div>
            <div class="mt-5 grid gap-5 md:grid-cols-3">
              <div>
                <label for="resource-style" class="account-label">资源形式</label>
                <select id="resource-style" v-model="profileDraft.preferred_resource_style" class="account-input focus-ring">
                  <option value="textual">概念讲解优先</option>
                  <option value="code_first">代码示例优先</option>
                  <option value="interactive">互动练习优先</option>
                  <option value="summary_first">总结提纲优先</option>
                </select>
              </div>
              <div>
                <label for="learning-pace" class="account-label">学习节奏</label>
                <select id="learning-pace" v-model="profileDraft.preferred_pace" class="account-input focus-ring">
                  <option value="gentle">从容</option>
                  <option value="steady">稳定</option>
                  <option value="intensive">紧凑</option>
                </select>
              </div>
              <div>
                <label for="practice-intensity" class="account-label">练习强度</label>
                <select id="practice-intensity" v-model="profileDraft.preferred_practice_intensity" class="account-input focus-ring">
                  <option value="light">轻量巩固</option>
                  <option value="balanced">均衡</option>
                  <option value="intensive">高频训练</option>
                </select>
              </div>
            </div>

            <div class="section-actions">
              <ActionFeedback v-if="profileFeedbackSection === 'learning'" :action="actions.profile" @retry="saveProfile('learning')" />
              <button type="submit" class="account-primary focus-ring" :disabled="actions.profile.status === 'loading'">
                {{ actions.profile.status === "loading" && profileFeedbackSection === "learning" ? "正在保存" : "保存学习偏好" }}
              </button>
            </div>
          </form>

          <form id="privacy" class="account-section" @submit.prevent="saveSettings">
            <div class="section-heading">
              <div>
                <h2>界面与隐私</h2>
                <p>选择跨设备界面偏好，以及哪些数据可用于改进和个性化服务。</p>
              </div>
            </div>

            <fieldset class="mt-6">
              <legend class="text-sm font-bold text-text-primary">界面偏好</legend>
              <div class="mt-3 max-w-xl">
                <div>
                  <label for="account-font-size" class="account-label">正文字号：{{ settingsDraft.preferences.font_size }}px</label>
                  <input id="account-font-size" v-model.number="settingsDraft.preferences.font_size" class="focus-ring min-h-11 w-full accent-primary" type="range" min="12" max="24" step="1" />
                </div>
              </div>
              <div class="account-divided mt-3">
                <div class="setting-row">
                  <label for="high-contrast" class="min-w-0 pr-4">
                    <strong>提高对比度</strong><span>增强文字、边框和交互控件的辨识度。</span>
                  </label>
                  <label for="high-contrast" class="checkbox-target focus-ring" aria-label="切换提高对比度">
                    <input id="high-contrast" v-model="settingsDraft.preferences.high_contrast" class="setting-checkbox" type="checkbox" />
                  </label>
                </div>
                <div class="setting-row">
                  <label for="reduce-motion" class="min-w-0 pr-4">
                    <strong>减少动态效果</strong><span>关闭不影响任务结果的过渡和动画。</span>
                  </label>
                  <label for="reduce-motion" class="checkbox-target focus-ring" aria-label="切换减少动态效果">
                    <input id="reduce-motion" v-model="settingsDraft.preferences.reduce_motion" class="setting-checkbox" type="checkbox" />
                  </label>
                </div>
              </div>
            </fieldset>

            <fieldset class="mt-8">
              <legend class="text-sm font-bold text-text-primary">隐私设置</legend>
              <div class="account-divided mt-3">
                <div class="setting-row">
                  <label for="personalization" class="min-w-0 pr-4">
                    <strong>个性化学习</strong><span>允许系统使用你的学习事件调整资源和复习节奏。</span>
                  </label>
                  <label for="personalization" class="checkbox-target focus-ring" aria-label="切换个性化学习">
                    <input id="personalization" v-model="settingsDraft.privacy.personalization_enabled" class="setting-checkbox" type="checkbox" />
                  </label>
                </div>
                <div class="setting-row">
                  <label for="analytics" class="min-w-0 pr-4">
                    <strong>产品分析</strong><span>允许使用去标识化的交互数据改进产品质量。</span>
                  </label>
                  <label for="analytics" class="checkbox-target focus-ring" aria-label="切换产品分析">
                    <input id="analytics" v-model="settingsDraft.privacy.analytics_enabled" class="setting-checkbox" type="checkbox" />
                  </label>
                </div>
                <div class="py-4">
                  <label for="profile-visibility" class="account-label">学习档案可见范围</label>
                  <select id="profile-visibility" v-model="settingsDraft.privacy.profile_visibility" class="account-input focus-ring max-w-sm">
                    <option value="private">仅自己</option>
                    <option value="teachers">授课教师</option>
                    <option value="public">所有人</option>
                  </select>
                </div>
              </div>
            </fieldset>

            <div class="section-actions">
              <ActionFeedback :action="actions.settings" @retry="saveSettings" />
              <button type="submit" class="account-primary focus-ring" :disabled="actions.settings.status === 'loading'">
                {{ actions.settings.status === "loading" ? "正在保存" : "保存界面与隐私设置" }}
              </button>
            </div>
          </form>

          <section id="security" class="account-section">
            <div class="section-heading">
              <div>
                <h2>设备与会话</h2>
                <p>检查已登录设备。撤销当前设备或全部会话后，需要重新登录。</p>
              </div>
              <button v-if="sessions.length" type="button" class="account-danger-secondary focus-ring" :disabled="actions.sessions.status === 'loading'" @click="requestRevokeAll">
                撤销全部会话
              </button>
            </div>

            <ul v-if="sessions.length" class="account-divided mt-6" aria-label="已登录设备列表">
              <li v-for="session in sessions" :key="sessionKey(session)" class="session-row">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <strong class="text-sm text-text-primary">{{ sessionName(session) }}</strong>
                    <span v-if="isCurrentSession(session)" class="rounded-full bg-success-soft px-2 py-1 text-xs font-semibold text-success-dark">当前设备</span>
                  </div>
                  <p class="mt-1 text-sm leading-5 text-text-secondary">{{ sessionDetails(session) }}</p>
                  <p class="mt-1 text-xs text-text-muted">最近活动：{{ formatDate(session.last_seen_at || session.last_active_at || session.updated_at || session.created_at) }}</p>
                </div>
                <button
                  type="button"
                  class="account-secondary focus-ring shrink-0"
                  :disabled="Boolean(revokingSessionId)"
                  :aria-label="`${isCurrentSession(session) ? '退出' : '撤销'} ${sessionName(session)} 的会话`"
                  @click="requestRevokeSession(session)"
                >
                  {{ revokingSessionId === sessionKey(session) ? "正在撤销" : isCurrentSession(session) ? "退出此设备" : "撤销" }}
                </button>
              </li>
            </ul>
            <div v-else class="mt-6 rounded-lg bg-space-elevated px-4 py-6 text-center text-sm text-text-secondary">没有可显示的设备会话。</div>
            <ActionFeedback :action="actions.sessions" @retry="retrySessionAction" />
          </section>

          <section id="data" class="account-section">
            <div class="section-heading">
              <div>
                <h2>数据与账户</h2>
                <p>导出你的资料、学习记录和设置，或永久注销账户。</p>
              </div>
            </div>

            <div class="mt-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <strong class="text-sm text-text-primary">导出我的数据</strong>
                <p class="mt-1 text-sm leading-5 text-text-secondary">生成 JSON 文件并下载到当前设备。</p>
              </div>
              <button type="button" class="account-secondary focus-ring shrink-0" :disabled="actions.export.status === 'loading'" @click="$emit('export-data')">
                {{ actions.export.status === "loading" ? "正在导出" : "下载数据副本" }}
              </button>
            </div>
            <ActionFeedback :action="actions.export" @retry="$emit('export-data')" />

            <div class="danger-zone mt-8 rounded-lg px-4 py-5 sm:px-5">
              <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <strong class="text-sm text-error">永久注销账户</strong>
                  <p class="mt-1 text-sm leading-5 text-text-secondary">此操作会删除账户资料，并撤销所有登录会话。</p>
                </div>
                <button v-if="!deleteExpanded" type="button" class="account-danger focus-ring shrink-0" @click="openDeleteConfirmation">注销账户</button>
              </div>

              <div v-if="deleteExpanded" class="mt-5 border-t border-subtle pt-5">
                <p class="text-sm leading-6 text-text-secondary">请输入用户名 <strong class="text-text-primary">{{ profile.user_id }}</strong>，并确认你理解此操作不可撤销。</p>
                <div class="mt-4 grid gap-4 sm:grid-cols-2">
                  <div>
                    <label for="delete-user-confirmation" class="account-label">确认用户名</label>
                    <input id="delete-user-confirmation" v-model="deleteConfirmation" class="account-input focus-ring" type="text" autocomplete="off" />
                  </div>
                  <div>
                    <label for="delete-password" class="account-label">当前密码</label>
                    <input id="delete-password" v-model="deletePassword" class="account-input focus-ring" type="password" autocomplete="current-password" required />
                  </div>
                </div>
                <div class="mt-4 flex min-h-11 items-center gap-3">
                  <label for="delete-acknowledgement" class="checkbox-target focus-ring" aria-label="确认永久删除账户">
                    <input id="delete-acknowledgement" v-model="deleteAcknowledged" class="setting-checkbox" type="checkbox" />
                  </label>
                  <label for="delete-acknowledgement" class="text-sm leading-5 text-text-secondary">我理解账户和相关数据将被永久删除。</label>
                </div>
                <ActionFeedback :action="actions.delete" @retry="confirmDelete" />
                <div class="mt-5 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                  <button type="button" class="account-secondary focus-ring" :disabled="actions.delete.status === 'loading'" @click="cancelDeleteConfirmation">取消</button>
                  <button type="button" class="account-danger focus-ring" :disabled="!canDelete || actions.delete.status === 'loading'" @click="confirmDelete">
                    {{ actions.delete.status === "loading" ? "正在注销" : "永久注销我的账户" }}
                  </button>
                </div>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, defineComponent, h, reactive, ref, watch } from "vue";

const props = defineProps({
  profile: { type: Object, required: true },
  settings: { type: Object, required: true },
  sessions: { type: Array, default: () => [] },
  currentSessionId: { type: String, default: "" },
  loading: { type: Boolean, default: false },
  loadError: { type: String, default: "" },
  actions: { type: Object, required: true },
  revokingSessionId: { type: String, default: "" },
});

const emit = defineEmits([
  "back",
  "retry-load",
  "save-profile",
  "save-settings",
  "request-verification",
  "retry-verification",
  "revoke-session",
  "revoke-all-sessions",
  "export-data",
  "delete-account",
]);

const ActionFeedback = defineComponent({
  props: { action: { type: Object, required: true } },
  emits: ["retry"],
  setup(feedbackProps, { emit: feedbackEmit }) {
    return () => {
      const action = feedbackProps.action || {};
      if (!action.message || (action.status !== "success" && action.status !== "error")) return null;
      const isError = action.status === "error";
      return h("div", {
        class: ["action-feedback", isError ? "action-feedback--error" : "action-feedback--success"],
        role: isError ? "alert" : "status",
      }, [
        h("span", { class: "min-w-0 leading-5" }, action.message),
        isError
          ? h("button", {
            type: "button",
            class: "focus-ring min-h-11 shrink-0 rounded-md px-3 font-semibold",
            onClick: () => feedbackEmit("retry"),
          }, "重试")
          : null,
      ]);
    };
  },
});

const navigation = [
  { id: "profile", label: "个人资料" },
  { id: "learning", label: "学习偏好" },
  { id: "privacy", label: "界面与隐私" },
  { id: "security", label: "设备与会话" },
  { id: "data", label: "数据与账户" },
];

const profileDraft = reactive({});
const settingsDraft = reactive({ preferences: {}, privacy: {} });
const profileFeedbackSection = ref("profile");
const emailPassword = ref("");
const lastSessionOperation = ref(null);
const deleteExpanded = ref(false);
const deleteConfirmation = ref("");
const deletePassword = ref("");
const deleteAcknowledged = ref(false);

const emailVerified = computed(() => Boolean(props.profile.email_verified || props.settings.email_verified));
const verifiedAt = computed(() => props.profile.email_verified_at || props.settings.email_verified_at || "");
const emailChanged = computed(() => String(profileDraft.email || "").trim() !== String(props.profile.email || "").trim());
const canDelete = computed(() => (
  deleteAcknowledged.value
  && Boolean(props.profile.user_id)
  && deleteConfirmation.value.trim() === String(props.profile.user_id)
  && Boolean(deletePassword.value)
));

watch(
  () => props.profile,
  (next) => {
    Object.assign(profileDraft, next || {});
    emailPassword.value = "";
  },
  { deep: true, immediate: true },
);

watch(
  () => props.settings,
  (next) => {
    Object.assign(settingsDraft, next || {});
    settingsDraft.preferences = { ...(next?.preferences || {}) };
    settingsDraft.privacy = { ...(next?.privacy || {}) };
  },
  { deep: true, immediate: true },
);

function editableProfile(section) {
  const payload = {
    display_name: String(profileDraft.display_name || "").trim(),
    email: String(profileDraft.email || "").trim(),
    university: String(profileDraft.university || "").trim(),
    major: String(profileDraft.major || "").trim(),
    grade: String(profileDraft.grade || "").trim(),
    weekly_study_hours: Math.max(0, Math.min(168, Number(profileDraft.weekly_study_hours) || 0)),
    learning_goal: String(profileDraft.learning_goal || "").trim(),
    preferred_resource_style: profileDraft.preferred_resource_style || "textual",
    preferred_pace: profileDraft.preferred_pace || "steady",
    preferred_practice_intensity: profileDraft.preferred_practice_intensity || "balanced",
  };
  if (section === "learning") {
    return {
      learning_goal: payload.learning_goal,
      preferred_resource_style: payload.preferred_resource_style,
      preferred_pace: payload.preferred_pace,
      preferred_practice_intensity: payload.preferred_practice_intensity,
    };
  }
  if (emailChanged.value) payload.current_password = emailPassword.value;
  return payload;
}

function saveProfile(section) {
  profileFeedbackSection.value = section;
  emit("save-profile", editableProfile(section));
}

function saveSettings() {
  emit("save-settings", {
    preferences: {
      theme: settingsDraft.preferences.theme || "system",
      high_contrast: Boolean(settingsDraft.preferences.high_contrast),
      reduce_motion: Boolean(settingsDraft.preferences.reduce_motion),
      font_size: Math.max(12, Math.min(24, Number(settingsDraft.preferences.font_size) || 16)),
    },
    privacy: {
      analytics_enabled: Boolean(settingsDraft.privacy.analytics_enabled),
      personalization_enabled: Boolean(settingsDraft.privacy.personalization_enabled),
      profile_visibility: settingsDraft.privacy.profile_visibility || "private",
    },
  });
}

function sessionKey(session) {
  return String(session?.session_id || session?.id || "unknown-session");
}

function isCurrentSession(session) {
  return Boolean(
    session?.is_current
    || session?.current
    || (props.currentSessionId && sessionKey(session) === props.currentSessionId),
  );
}

function sessionName(session) {
  const explicitName = String(session?.device_name || "").trim();
  if (explicitName && !/(Mozilla\/|AppleWebKit\/|Chrome\/|Safari\/|Firefox\/|Edg\/)/i.test(explicitName)) {
    return explicitName;
  }
  const userAgent = String(session?.user_agent || explicitName);
  const browser = /Edg\//i.test(userAgent)
    ? "Edge"
    : /Firefox\//i.test(userAgent)
      ? "Firefox"
      : /Chrome\//i.test(userAgent)
        ? "Chrome"
        : /Safari\//i.test(userAgent)
          ? "Safari"
          : session?.browser || "未知浏览器";
  const os = /Windows/i.test(userAgent)
    ? "Windows"
    : /Android/i.test(userAgent)
      ? "Android"
      : /iPhone|iPad|iPod/i.test(userAgent)
        ? "iOS"
        : /Mac OS/i.test(userAgent)
          ? "macOS"
          : /Linux/i.test(userAgent)
            ? "Linux"
            : session?.os || "未知系统";
  return `${browser} · ${os}`;
}

function sessionDetails(session) {
  const pieces = [session?.location, session?.ip_address || session?.ip].filter(Boolean);
  return pieces.join(" · ") || "位置和网络信息不可用";
}

function formatDate(value) {
  if (!value) return "未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function requestRevokeSession(session) {
  lastSessionOperation.value = { type: "single", session };
  emit("revoke-session", session);
}

function requestRevokeAll() {
  lastSessionOperation.value = { type: "all" };
  emit("revoke-all-sessions");
}

function retrySessionAction() {
  if (lastSessionOperation.value?.type === "single") {
    emit("revoke-session", lastSessionOperation.value.session);
  } else {
    emit("revoke-all-sessions");
  }
}

function openDeleteConfirmation() {
  deleteExpanded.value = true;
}

function cancelDeleteConfirmation() {
  if (props.actions.delete.status === "loading") return;
  deleteExpanded.value = false;
  deleteConfirmation.value = "";
  deletePassword.value = "";
  deleteAcknowledged.value = false;
}

function confirmDelete() {
  if (!canDelete.value || props.actions.delete.status === "loading") return;
  emit("delete-account", {
    confirmation: "DELETE",
    password: deletePassword.value,
  });
}
</script>

<style scoped>
.account-layout {
  display: grid;
  gap: 1.5rem;
  align-items: start;
}

.account-main {
  border: 1px solid var(--border-subtle);
  box-shadow: var(--workspace-shadow-soft);
}

.account-nav {
  display: flex;
  gap: 0.25rem;
  overflow-x: auto;
  padding-bottom: 0.25rem;
}

.account-nav a {
  display: inline-flex;
  min-height: 2.75rem;
  flex: 0 0 auto;
  align-items: center;
  border-radius: 0.5rem;
  padding: 0.65rem 0.8rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
  font-weight: 650;
}

.account-nav a:hover {
  background: var(--color-primary-soft);
  color: var(--color-primary-dark);
}

.account-section {
  scroll-margin-top: 5rem;
  padding: 1.5rem 1.25rem;
}

.account-section + .account-section {
  border-top: 1px solid var(--border-subtle);
}

.section-heading {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.section-heading h2 {
  color: var(--text-primary);
  font-size: 1.125rem;
  font-weight: 800;
}

.section-heading p {
  margin-top: 0.35rem;
  max-width: 65ch;
  color: var(--text-secondary);
  font-size: 0.875rem;
  line-height: 1.5rem;
}

.account-label {
  display: block;
  margin-bottom: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.8125rem;
  font-weight: 700;
}

.account-input {
  min-height: 2.75rem;
  width: 100%;
  border: 1px solid var(--border-subtle);
  border-radius: 0.5rem;
  background: var(--input-bg);
  padding: 0.7rem 0.875rem;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.account-input::placeholder {
  color: var(--text-muted);
}

.account-input:hover {
  border-color: var(--border-hover);
}

.account-primary,
.account-secondary,
.account-danger,
.account-danger-secondary {
  display: inline-flex;
  min-height: 2.75rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  padding: 0.65rem 1rem;
  font-size: 0.875rem;
  font-weight: 700;
  transition: background-color 160ms ease-out, border-color 160ms ease-out, color 160ms ease-out;
}

.account-primary {
  background: var(--color-primary);
  color: var(--color-primary-text);
}

.account-primary:hover:not(:disabled) {
  background: var(--color-primary-dark);
}

.account-secondary {
  border: 1px solid var(--border-subtle);
  background: var(--space-panel);
  color: var(--text-secondary);
}

.account-secondary:hover:not(:disabled) {
  border-color: var(--border-hover);
  background: var(--space-elevated);
  color: var(--text-primary);
}

.account-danger {
  background: var(--color-error);
  color: var(--color-error-text);
}

.account-danger:hover:not(:disabled) {
  background: var(--color-error-dark);
}

.account-danger-secondary {
  border: 1px solid color-mix(in srgb, var(--color-error) 36%, var(--border-subtle));
  background: var(--space-panel);
  color: var(--color-error);
}

.account-danger-secondary:hover:not(:disabled) {
  background: var(--color-error-soft);
}

.account-primary:disabled,
.account-secondary:disabled,
.account-danger:disabled,
.account-danger-secondary:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.section-actions {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  align-items: stretch;
  margin-top: 1.5rem;
}

.action-feedback {
  display: flex;
  min-height: 2.75rem;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: 1rem;
  border-radius: 0.5rem;
  padding: 0.6rem 0.75rem 0.6rem 1rem;
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}

.section-actions .action-feedback {
  margin-top: 0;
}

.action-feedback--success {
  background: var(--color-success-soft);
  color: var(--color-success);
}

.action-feedback--error {
  background: var(--color-error-soft);
  color: var(--color-error);
}

.setting-row {
  display: flex;
  min-height: 4rem;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding-block: 0.75rem;
}

.account-divided > * + * {
  border-top: 1px solid var(--border-subtle);
}

.setting-row label {
  cursor: pointer;
}

.setting-row strong,
.setting-row span {
  display: block;
}

.setting-row strong {
  color: var(--text-primary);
  font-size: 0.875rem;
}

.setting-row span {
  margin-top: 0.25rem;
  color: var(--text-secondary);
  font-size: 0.8125rem;
  line-height: 1.25rem;
}

.setting-checkbox {
  width: 1.25rem;
  height: 1.25rem;
  flex: 0 0 auto;
  accent-color: var(--color-primary);
}

.checkbox-target {
  display: inline-flex;
  min-width: 2.75rem;
  min-height: 2.75rem;
  flex: 0 0 auto;
  cursor: pointer;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
}

.checkbox-target:hover {
  background: var(--space-elevated);
}

.session-row {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-block: 1rem;
}

.session-row strong,
.session-row p {
  overflow-wrap: anywhere;
}

.danger-zone {
  border: 1px solid color-mix(in srgb, var(--color-error) 28%, var(--border-subtle));
  background: var(--color-error-soft);
}

.skeleton-line {
  background: var(--space-elevated);
  animation: account-pulse 1.5s ease-in-out infinite;
}

@keyframes account-pulse {
  50% { opacity: 0.55; }
}

@media (min-width: 640px) {
  .section-heading,
  .session-row {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }

  .section-actions {
    flex-direction: row;
    align-items: center;
    justify-content: flex-end;
  }

  .section-actions .action-feedback {
    margin-right: auto;
  }
}

@media (min-width: 900px) {
  .account-layout {
    grid-template-columns: 12.5rem minmax(0, 1fr);
  }

  .account-nav {
    position: sticky;
    top: 5rem;
    flex-direction: column;
    overflow: visible;
  }

  .account-section {
    padding: 2rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton-line {
    animation: none;
  }
}
</style>
