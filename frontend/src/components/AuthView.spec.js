import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const serviceMocks = vi.hoisted(() => ({
  getCaptcha: vi.fn(),
}));

vi.mock("../services/eduAgentApi", () => ({
  getCaptcha: serviceMocks.getCaptcha,
}));

import AuthView from "./AuthView.vue";

const RouterLinkStub = {
  template: "<a><slot /></a>",
};

function mountAuth(overrides = {}) {
  return mount(AuthView, {
    props: {
      screen: "login",
      submitLogin: vi.fn(async () => undefined),
      submitRegister: vi.fn(async () => undefined),
      submitForgot: vi.fn(async () => undefined),
      submitReset: vi.fn(async () => undefined),
      submitVerification: vi.fn(async () => undefined),
      ...overrides,
    },
    global: {
      stubs: { RouterLink: RouterLinkStub },
    },
  });
}

describe("AuthView async failures", () => {
  beforeEach(() => {
    serviceMocks.getCaptcha.mockResolvedValue({
      captcha_token: "captcha-token",
      svg: '<svg xmlns="http://www.w3.org/2000/svg" />',
    });
  });

  it("catches a rejected login callback and renders a retryable error", async () => {
    const submitLogin = vi.fn().mockRejectedValue(new Error("credentials rejected"));
    const wrapper = mountAuth({ submitLogin });
    await flushPromises();

    await wrapper.get("#auth-user-id").setValue("student");
    await wrapper.get("#auth-password").setValue("secret123");
    await wrapper.get("#auth-captcha").setValue("4");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(submitLogin).toHaveBeenCalledWith(
      "student",
      "secret123",
      "captcha-token",
      "4",
    );
    expect(wrapper.get('[role="alert"]').text()).toContain("credentials rejected");
    expect(wrapper.get('[role="alert"] button').text()).toBe("重试");
    expect(wrapper.get('button[type="submit"]').attributes("disabled")).toBeUndefined();
  });
});
