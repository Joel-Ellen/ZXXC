// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { nextTick, reactive } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const testState = vi.hoisted(() => ({
  agent: null,
  recordCodeSubmission: vi.fn(),
  route: null,
  router: {
    push: vi.fn(async () => undefined),
    replace: vi.fn(async () => undefined),
  },
}));

vi.mock("vue-router", () => ({
  useRoute: () => testState.route,
  useRouter: () => testState.router,
}));

vi.mock("../services/eduAgentApi", () => ({
  prepareSessionReviewRetest: vi.fn(),
}));

vi.mock("../composables/useEduAgent", async () => {
  const { ref } = await import("vue");
  const resolved = vi.fn(async (value = null) => value);
  testState.agent = {
    activeCourse: ref({ course_id: "course-A" }),
    agentFeedback: ref([]),
    agentStatuses: ref([]),
    bootMode: ref("ready"),
    currentCards: ref([]),
    currentNode: ref("N-current"),
    currentNodeTitle: ref("Current node"),
    currentPathNodes: ref([{ id: "N-current", title: "Current node" }]),
    currentUser: ref({ user_id: "learner" }),
    enrolledCourses: ref([]),
    infoMessage: ref(""),
    isBusy: ref(false),
    isLoadingNode: ref(false),
    isSubmittingProbe: ref(false),
    lastDiagnostic: ref(null),
    masteredCount: ref(0),
    messages: ref([]),
    overallProgress: ref(0),
    probe: ref(null),
    probeCollected: ref(0),
    probeTotal: ref(0),
    sessionId: ref("learner:course-A"),
    endLearningSession: resolved,
    flushLearningActivity: resolved,
    getAgentLabel: vi.fn(() => "Agent"),
    getCardLabel: vi.fn(() => "Card"),
    handleLogout: resolved,
    parseQuiz: vi.fn(() => null),
    prepareLearningRoute: vi.fn(async (courseId, nodeId) => ({ status: "ready", courseId, nodeId })),
    recordAnswerSelection: resolved,
    recordCodeRun: resolved,
    recordCodeSubmission: testState.recordCodeSubmission,
    recordContentView: resolved,
    recordHintRequest: resolved,
    refreshNodeResources: resolved,
    sendTutorMessage: resolved,
    startLearningSession: resolved,
    submitProbe: resolved,
    submitQuiz: resolved,
  };
  return { useEduAgent: () => testState.agent };
});

import LearnView from "./LearnView.vue";

const PremiumWorkspaceStub = {
  name: "PremiumWorkspace",
  emits: ["code-submitted"],
  template: "<div />",
};

let warningSpy;

async function settleUi() {
  await Promise.resolve();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  await nextTick();
}

function codeResult(nodeId, resourceId, submissionId) {
  return {
    sessionId: "learner:course-A",
    nodeId,
    resourceId,
    attemptNumber: 1,
    result: { status: "ok", submission_id: submissionId, verdict: "accepted" },
  };
}

beforeEach(() => {
  setActivePinia(createPinia());
  warningSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  testState.route = reactive({
    query: {},
    params: { courseId: "course-A", nodeId: "N-current" },
    fullPath: "/learn/course-A/N-current",
  });
  testState.recordCodeSubmission.mockReset();
  testState.router.push.mockClear();
  testState.router.replace.mockClear();
});

afterEach(() => {
  warningSpy.mockRestore();
  vi.clearAllMocks();
});

describe("LearnView pending code event ledger", () => {
  it("removes only the event that succeeded while retaining other failures", async () => {
    testState.recordCodeSubmission.mockRejectedValue(new Error("ledger unavailable"));
    const wrapper = mount(LearnView, {
      props: { courseId: "course-A", nodeId: "N-current" },
      global: {
        stubs: {
          AppPageFrame: { template: "<div><slot /></div>" },
          PremiumWorkspace: PremiumWorkspaceStub,
        },
      },
    });
    await settleUi();

    const workspace = wrapper.findComponent(PremiumWorkspaceStub);
    workspace.vm.$emit("code-submitted", codeResult("N01", "resource-1", "submission-1"));
    workspace.vm.$emit("code-submitted", codeResult("N02", "resource-2", "submission-2"));
    await settleUi();
    expect(wrapper.text()).toContain("2 次代码判题结果尚未保存");

    testState.recordCodeSubmission.mockImplementation((event) => (
      event.resourceId === "resource-1"
        ? Promise.resolve({})
        : Promise.reject(new Error("still unavailable"))
    ));
    await wrapper.get("button").trigger("click");
    await settleUi();
    expect(wrapper.text()).toContain("N02 的判题结果已显示，但学习记录尚未保存");
    expect(wrapper.text()).not.toContain("N01 的判题结果已显示");

    testState.recordCodeSubmission.mockResolvedValue({});
    await wrapper.get("button").trigger("click");
    await settleUi();
    expect(wrapper.text()).not.toContain("学习记录尚未保存");

    wrapper.unmount();
  });
});
