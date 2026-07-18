// Single source of truth for auth token persistence.
// Zero-dependency on purpose: importable from apiClient, clientTelemetry,
// composables, and Pinia stores without cycles.
// Uses globalThis so it stays inert in non-browser environments (vitest node env).
export const ACCESS_TOKEN_KEY = "access_token";
export const REFRESH_TOKEN_KEY = "refresh_token";

export const tokenStore = {
  getAccessToken() {
    return globalThis.localStorage?.getItem(ACCESS_TOKEN_KEY) ?? null;
  },
  getRefreshToken() {
    return globalThis.localStorage?.getItem(REFRESH_TOKEN_KEY) ?? null;
  },
  setTokens({ accessToken, refreshToken }) {
    if (accessToken) {
      globalThis.localStorage?.setItem(ACCESS_TOKEN_KEY, accessToken);
    }
    if (refreshToken) {
      globalThis.localStorage?.setItem(REFRESH_TOKEN_KEY, refreshToken);
    }
  },
  clear() {
    globalThis.localStorage?.removeItem(ACCESS_TOKEN_KEY);
    globalThis.localStorage?.removeItem(REFRESH_TOKEN_KEY);
  },
};

export default tokenStore;
