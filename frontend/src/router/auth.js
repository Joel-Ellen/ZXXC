import { refreshToken } from "../services/eduAgentApi";
import { tokenStore } from "../services/apiClient";

let pendingCheck = null;

async function fetchCurrentUser() {
  const accessToken = tokenStore.getAccessToken();
  if (!accessToken) {
    return null;
  }

  const response = await window.fetch("/api/auth/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
    credentials: "include",
  });

  if (!response.ok) {
    return null;
  }

  return response.json();
}

/**
 * Resolve the current user before entering a protected route. The check uses a
 * direct request so the axios response interceptor cannot replace a deep link
 * with a hard navigation when an expired access token is refreshed.
 */
export async function ensureAuthenticated() {
  if (typeof window === "undefined") {
    return null;
  }

  if (pendingCheck) {
    return pendingCheck;
  }

  pendingCheck = (async () => {
    if (!tokenStore.getAccessToken() && !tokenStore.getRefreshToken()) {
      return null;
    }

    try {
      const currentUser = await fetchCurrentUser();
      if (currentUser) {
        return currentUser;
      }

      await refreshToken();
      const refreshedUser = await fetchCurrentUser();
      if (refreshedUser) {
        return refreshedUser;
      }
    } catch {
      // An invalid or expired token is treated as an unauthenticated visit.
    }

    tokenStore.clear();
    return null;
  })();

  try {
    return await pendingCheck;
  } finally {
    pendingCheck = null;
  }
}
