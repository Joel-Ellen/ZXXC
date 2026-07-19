import axios from "axios";
import { tokenStore } from "./tokenStore";

export function createRequestId() {
  if (typeof window !== "undefined" && window.crypto?.randomUUID) {
    return window.crypto.randomUUID().replaceAll("-", "");
  }
  return `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
}

export { tokenStore };

let refreshPromise = null;

export function refreshStoredTokens() {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const refreshToken = tokenStore.getRefreshToken();
    const response = await axios.post(
      "/api/auth/refresh",
      refreshToken ? { refresh_token: refreshToken } : {},
      { withCredentials: true, timeout: 30000 },
    );
    const accessToken = response.data.access_token;
    if (!accessToken) throw new Error("登录状态已失效，请重新登录。");
    tokenStore.setTokens({
      accessToken,
      refreshToken: response.data.refresh_token,
    });
    return accessToken;
  })().finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
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
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const accessToken = await refreshStoredTokens();
        originalRequest.headers = originalRequest.headers ?? {};
        originalRequest.headers.Authorization = `Bearer ${accessToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        tokenStore.clear();
        window.location.assign("/?reason=SECURITY_BREACH_FORCED_OUT");
      }
    }

    return Promise.reject(error);
  },
);

export default apiClient;
