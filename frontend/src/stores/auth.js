import { defineStore } from "pinia";
import { ref } from "vue";
import {
  fetchMyProfile,
  login as loginRequest,
  refreshToken,
  register as registerRequest,
} from "../services/eduAgentApi";
import { tokenStore } from "../services/tokenStore";

// Auth state extracted from useEduAgent.js. The composable delegates here so
// its returned API (currentUser / isLoggedIn / handleLogin / ...) is unchanged
// for the views.
export const useAuthStore = defineStore("auth", () => {
  const currentUser = ref(null);
  const isLoggedIn = ref(false);

  async function tryAutoLogin() {
    const token = tokenStore.getAccessToken();
    if (!token) {
      return false;
    }

    try {
      currentUser.value = await fetchMyProfile();
      isLoggedIn.value = true;
      return true;
    } catch {
      try {
        await refreshToken();
        currentUser.value = await fetchMyProfile();
        isLoggedIn.value = true;
        return true;
      } catch {
        tokenStore.clear();
        return false;
      }
    }
  }

  async function login(userIdInput, password, captchaToken, captchaAnswer) {
    const result = await loginRequest({
      user_id: userIdInput,
      password,
      captcha_token: captchaToken,
      captcha_answer: captchaAnswer,
    });
    currentUser.value = result.user;
    isLoggedIn.value = true;
    return result;
  }

  async function register(userIdInput, email, password, captchaToken, captchaAnswer) {
    const result = await registerRequest({
      user_id: userIdInput,
      email,
      password,
      captcha_token: captchaToken,
      captcha_answer: captchaAnswer,
    });
    currentUser.value = result.user;
    isLoggedIn.value = true;
    return result;
  }

  function logout() {
    tokenStore.clear();
    currentUser.value = null;
    isLoggedIn.value = false;
  }

  return { currentUser, isLoggedIn, tryAutoLogin, login, register, logout };
});
