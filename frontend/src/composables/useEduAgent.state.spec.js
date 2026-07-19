import { createPinia, setActivePinia } from "pinia";
import { describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../stores/auth";
import { useEduAgent } from "./useEduAgent";

describe("EduAgent Pinia state", () => {
  it("shares one composable instance and delegates authentication to the auth store", async () => {
    setActivePinia(createPinia());

    const auth = useAuthStore();
    const login = vi.spyOn(auth, "login").mockResolvedValue({ user: { user_id: "login-user" } });
    const register = vi.spyOn(auth, "register").mockResolvedValue({ user: { user_id: "new-user" } });
    const logout = vi.spyOn(auth, "logout");
    const firstConsumer = useEduAgent();
    const secondConsumer = useEduAgent();

    expect(secondConsumer).toBe(firstConsumer);

    auth.currentUser = { user_id: "pinia-user" };
    auth.isLoggedIn = true;
    expect(firstConsumer.currentUser.value).toEqual({ user_id: "pinia-user" });
    expect(secondConsumer.isLoggedIn.value).toBe(true);

    await firstConsumer.handleLogin("login-user", "secret", "captcha-token", "captcha-answer");
    expect(login).toHaveBeenCalledWith("login-user", "secret", "captcha-token", "captcha-answer");

    await firstConsumer.handleRegister(
      "new-user",
      "new-user@example.com",
      "secret",
      "captcha-token",
      "captcha-answer",
    );
    expect(register).toHaveBeenCalledWith(
      "new-user",
      "new-user@example.com",
      "secret",
      "captcha-token",
      "captcha-answer",
    );

    firstConsumer.handleLogout();
    expect(logout).toHaveBeenCalledOnce();
    expect(firstConsumer.currentUser.value).toBeNull();
    expect(secondConsumer.isLoggedIn.value).toBe(false);
  });
});
