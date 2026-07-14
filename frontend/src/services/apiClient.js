import axios from "axios";

const ACCESS_TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";

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
        window.location.assign("/?reason=SECURITY_BREACH_FORCED_OUT");
      }
    }

    return Promise.reject(error);
  },
);

export default apiClient;
