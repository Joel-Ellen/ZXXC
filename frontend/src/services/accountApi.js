import apiClient from "./apiClient";

const ERROR_MESSAGES = {
  ACCOUNT_DELETION_CONFIRMATION_REQUIRED: "用户名、确认项或当前密码不正确。",
  PROFILE_REAUTHENTICATION_REQUIRED: "更换邮箱前，请输入正确的当前密码。",
  RESET_TOKEN_INVALID_OR_EXPIRED: "重置链接无效或已过期，请重新申请。",
  VERIFICATION_TOKEN_INVALID_OR_EXPIRED: "验证链接无效或已过期，请重新发送验证邮件。",
  SESSION_NOT_FOUND: "该设备会话已不存在，请刷新后重试。",
  SESSION_REVOKED: "此设备会话已撤销，请重新登录。",
  TOKEN_REVOKED: "登录凭证已失效，请重新登录。",
  delivery_not_configured: "邮件服务尚未配置，请联系管理员。",
  delivery_failed: "邮件发送失败，请稍后重试。",
  profile_email_invalid: "请输入有效的邮箱地址。",
  profile_display_name_too_long: "显示名称不能超过 128 个字符。",
  profile_weekly_study_hours_invalid: "每周学习时长需在 0 至 168 小时之间。",
  privacy_profile_visibility_invalid: "学习档案可见范围无效。",
  settings_theme_invalid: "主题设置无效。",
  settings_font_size_invalid: "正文字号需在 12 至 24 像素之间。",
};

function responseData(response) {
  return response?.data ?? {};
}

export async function getUserProfile() {
  return responseData(await apiClient.get("/user/profile"));
}

export async function updateUserProfile(profile) {
  return responseData(await apiClient.patch("/user/profile", profile));
}

export async function getUserSettings() {
  return responseData(await apiClient.get("/user/settings"));
}

export async function updateUserSettings(settings) {
  return responseData(await apiClient.patch("/user/settings", settings));
}

export async function requestPasswordReset(email) {
  return responseData(await apiClient.post("/auth/password/forgot", { email }));
}

export async function resetPassword({ token, newPassword }) {
  return responseData(await apiClient.post("/auth/password/reset", {
    token,
    new_password: newPassword,
  }));
}

export async function requestEmailVerification() {
  return responseData(await apiClient.post("/auth/email-verification/request"));
}

export async function verifyEmail(token) {
  return responseData(await apiClient.post("/auth/email-verification/verify", { token }));
}

export async function getDeviceSessions() {
  return responseData(await apiClient.get("/auth/sessions"));
}

export async function revokeDeviceSession(sessionId) {
  return responseData(await apiClient.delete(`/auth/sessions/${encodeURIComponent(sessionId)}`));
}

export async function revokeAllDeviceSessions() {
  return responseData(await apiClient.delete("/auth/sessions"));
}

function filenameFromDisposition(disposition) {
  if (!disposition) return "eduagent-data-export.json";

  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      return encoded;
    }
  }

  return disposition.match(/filename="?([^";]+)"?/i)?.[1] || "eduagent-data-export.json";
}

export async function exportUserData() {
  const response = await apiClient.get("/user/export", {
    responseType: "blob",
    timeout: 60_000,
  });
  return {
    blob: response.data,
    filename: filenameFromDisposition(response.headers?.["content-disposition"]),
  };
}

export async function deleteUserAccount({ password, confirmation = "DELETE" }) {
  return responseData(await apiClient.delete("/user/account", {
    data: {
      confirmation,
      password,
    },
  }));
}

export function accountApiError(error, fallback = "操作失败，请稍后重试。") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return ERROR_MESSAGES[detail] || detail;
  }
  if (detail && typeof detail === "object") {
    return detail.message || detail.error || fallback;
  }
  if (typeof error?.message === "string" && error.message.trim()) {
    return error.message === "Network Error" ? "无法连接服务器，请检查网络后重试。" : error.message;
  }
  return fallback;
}
