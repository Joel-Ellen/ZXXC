import axios from "axios";
import { captureApiError } from "./errorMonitoring";

const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";
const PUBLIC_AUTH_PATHS = new Set([
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
  "/auth/captcha",
  "/auth/captcha-json",
  "/auth/password/forgot",
  "/auth/password/reset",
  "/auth/email-verification/verify",
]);

export function createRequestId() {
  if (typeof window !== "undefined" && window.crypto?.randomUUID) {
    return window.crypto.randomUUID().replaceAll("-", "");
  }
  return `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
}

export const tokenStore = {
  getAccessToken() {
    return window.localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  getRefreshToken() {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  setTokens({ accessToken, refreshToken }) {
    if (accessToken) {
      window.localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    }
    if (refreshToken) {
      window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
    }
  },
  clear() {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

function isPublicAuthRequest(config) {
  const url = String(config?.url || "").split("?", 1)[0];
  return PUBLIC_AUTH_PATHS.has(url);
}

const apiClient = axios.create({
  baseURL: "/api",
  timeout: 30000,
  withCredentials: true,
});

apiClient.interceptors.request.use((config) => {
  const token = tokenStore.getAccessToken();
  config.headers = config.headers ?? {};
  if (!config.headers["X-Request-ID"]) {
    config.headers["X-Request-ID"] = createRequestId();
  }
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config ?? {};
    if (
      error.response?.status === 401
      && !originalRequest._retry
      && !isPublicAuthRequest(originalRequest)
    ) {
      originalRequest._retry = true;

      try {
        const refreshToken = tokenStore.getRefreshToken();
        const res = await axios.post(
          "/api/auth/refresh",
          refreshToken ? { refresh_token: refreshToken } : {},
          { withCredentials: true, timeout: 30000 },
        );

        if (res.status === 200) {
          const accessToken = res.data.access_token;
          const nextRefreshToken = res.data.refresh_token;
          tokenStore.setTokens({ accessToken, refreshToken: nextRefreshToken });
          originalRequest.headers = originalRequest.headers ?? {};
          originalRequest.headers.Authorization = `Bearer ${accessToken}`;
          return apiClient(originalRequest);
        }
      } catch (refreshError) {
        tokenStore.clear();
        const currentPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        window.location.assign(`/login?redirect=${encodeURIComponent(currentPath)}&reason=SECURITY_BREACH_FORCED_OUT`);
      }
    }

    const requestHeaders = originalRequest.headers ?? {};
    captureApiError(error, {
      requestId: requestHeaders["X-Request-ID"] || requestHeaders["x-request-id"] || "",
      method: originalRequest.method || "",
      endpoint: String(originalRequest.url || "").split("?", 1)[0],
    });

    return Promise.reject(error);
  },
);

export default apiClient;
