// @vitest-environment jsdom

import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const assetApiMocks = vi.hoisted(() => ({
  fetchSessionLearningAssets: vi.fn(async () => ({ assets: {}, revision: 0 })),
  patchSessionLearningAssets: vi.fn(async () => ({ assets: {}, revision: 1 })),
}));

vi.mock("../services/eduAgentApi", () => assetApiMocks);

import ChatArea from "./ChatArea.vue";
import { useLearningAssetsStore } from "../stores/learningAssets";

function mountChat(sessionId, nodeId) {
  return mount(ChatArea, {
    props: {
      sessionId,
      nodeId,
      bootMode: "ready",
    },
    global: {
      stubs: {
        MarkdownContent: true,
        ProbeDeck: true,
        StreamText: true,
      },
    },
  });
}

beforeEach(() => {
  window.localStorage.clear();
  setActivePinia(createPinia());
});

describe("ChatArea learning asset scopes", () => {
  it("saves the final N01 edit and scroll position under N01 before opening N02", async () => {
    const assets = useLearningAssetsStore();
    assets.setSession("session-course-A");
    const wrapper = mountChat("session-course-A", "N01");

    await wrapper.get("#chat-input").setValue("N01 final character Z");
    const scrollRoot = wrapper.get("[data-chat-scroll='true']");
    scrollRoot.element.scrollTop = 137;

    await wrapper.setProps({ nodeId: "N02" });

    expect(assets.read("drafts", "tutor:N01")).toMatchObject({
      node_id: "N01",
      content: "N01 final character Z",
    });
    expect(assets.read("scroll_positions", "chat:N01")).toMatchObject({
      node_id: "N01",
      top: 137,
    });
    expect(wrapper.get("#chat-input").element.value).toBe("");

    wrapper.unmount();
  });

  it("keeps the same node isolated between course sessions", async () => {
    const assets = useLearningAssetsStore();
    assets.setSession("session-course-A");
    const wrapper = mountChat("session-course-A", "N01");

    await wrapper.get("#chat-input").setValue("course A draft");
    await wrapper.vm.flushLearningAssets();

    assets.setSession("session-course-B");
    await wrapper.setProps({ sessionId: "session-course-B" });
    expect(wrapper.get("#chat-input").element.value).toBe("");

    await wrapper.get("#chat-input").setValue("course B draft");
    await wrapper.vm.flushLearningAssets();

    assets.setSession("session-course-A");
    await wrapper.setProps({ sessionId: "session-course-A" });
    expect(wrapper.get("#chat-input").element.value).toBe("course A draft");

    wrapper.unmount();
  });

  it("restores the last character after an immediate logout and login", async () => {
    const sessionId = "session-immediate-logout";
    const assets = useLearningAssetsStore();
    assets.setSession(sessionId);
    const wrapper = mountChat(sessionId, "N01");

    await wrapper.get("#chat-input").setValue("keep the last character Z");
    const pendingFlush = wrapper.vm.flushLearningAssets();
    assets.reset();
    wrapper.unmount();
    await pendingFlush;

    assets.setSession(sessionId);
    const restored = mountChat(sessionId, "N01");
    expect(restored.get("#chat-input").element.value).toBe("keep the last character Z");

    restored.unmount();
  });
});
