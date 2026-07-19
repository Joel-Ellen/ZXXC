import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { describe, expect, it, vi } from "vitest";

const routerPush = vi.hoisted(() => vi.fn());

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: routerPush }),
}));

import PremiumWorkspace from "./PremiumWorkspace.vue";

const WorkspaceShellStub = {
  name: "WorkspaceShell",
  template: `
    <div>
      <slot name="header" />
      <slot />
      <slot name="drawer" />
      <slot name="overlay" />
    </div>
  `,
};

const ResourceCanvasStub = {
  name: "ResourceCanvas",
  props: {
    sessionId: { type: String, default: "" },
  },
  emits: ["code-run", "code-submitted"],
  template: "<section />",
};

describe("PremiumWorkspace code practice wiring", () => {
  it("passes the session through both workspace layers and forwards code events", async () => {
    const wrapper = mount(PremiumWorkspace, {
      props: {
        bootMode: "ready",
        sessionId: "learner:course-a",
        currentNode: "N01",
        cards: [],
        pathNodes: [],
        nodeTitle: "Node 01",
        getCardLabel: (type) => type,
        getAgentLabel: () => "Agent",
        parseQuiz: () => [],
      },
      global: {
        stubs: {
          WorkspaceShell: WorkspaceShellStub,
          SessionHeader: true,
          SidebarDrawer: true,
          TutorPane: true,
          ResourceCanvas: ResourceCanvasStub,
        },
      },
    });

    const canvas = wrapper.findComponent(ResourceCanvasStub);
    expect(canvas.exists()).toBe(true);
    expect(canvas.props("sessionId")).toBe("learner:course-a");

    const run = { nodeId: "N01", resourceId: "code-1", result: { mode: "run" } };
    const submission = { nodeId: "N01", resourceId: "code-1", result: { mode: "submit" } };
    canvas.vm.$emit("code-run", run);
    canvas.vm.$emit("code-submitted", submission);
    await nextTick();

    expect(wrapper.emitted("code-run")).toEqual([[run]]);
    expect(wrapper.emitted("code-submitted")).toEqual([[submission]]);
    wrapper.unmount();
  });
});
