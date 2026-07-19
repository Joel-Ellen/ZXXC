// @vitest-environment jsdom

import { createPinia, setActivePinia } from "pinia";
import { EditorView } from "@codemirror/view";
import { mount } from "@vue/test-utils";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const serviceMocks = vi.hoisted(() => ({
  fetchSessionLearningAssets: vi.fn(async () => ({ assets: {}, revision: 0 })),
  patchSessionLearningAssets: vi.fn(async () => ({ assets: {}, revision: 1 })),
  fetchSessionPracticeProblem: vi.fn(),
  runSessionPractice: vi.fn(),
  submitSessionPractice: vi.fn(),
}));

vi.mock("../services/eduAgentApi", () => serviceMocks);

import CodePracticePanel from "./CodePracticePanel.vue";
import ResourceCanvas from "./ResourceCanvas.vue";
import { useLearningAssetsStore } from "../stores/learningAssets";

function deferred() {
  let resolve; let reject;
  const promise = new Promise((resolveP, rejectP) => { resolve = resolveP; reject = rejectP; });
  return { promise, resolve, reject };
}

async function settleUi() {
  await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
  await Promise.resolve();
}

function quizCard(nodeId) {
  return {
    resource_id: `quiz-${nodeId}`,
    resource_type: "diagnostic_quiz",
    title: `${nodeId} diagnostic`,
    structured_payload: {
      questions: [{
        id: `question-${nodeId}`,
        prompt: `${nodeId} question`,
        options: [`${nodeId} option A`, `${nodeId} option B`],
      }],
    },
  };
}

function conceptCard(nodeId) {
  return {
    resource_id: `concept-${nodeId}`,
    resource_type: "concept_map",
    title: `${nodeId} concept`,
    structured_payload: {
      summary: "Concept summary",
      definition: `${nodeId} definition text`,
      constraints: ["constraint one"],
      mechanism: ["mechanism step"],
      prerequisites: ["prior knowledge"],
      learning_objectives: ["objective 1"],
      sections: [{ heading: "Mechanism", body: "Explanation body" }],
      bullets: ["bullet point 1"],
      common_misconceptions: ["common mistake"],
      counterexamples: ["wrong approach"],
      transfer_questions: ["related problem?"],
      review_prompts: ["review this concept"],
      mermaid_source: "graph TD\nA[Start] --> B[End]",
    },
  };
}

function findButton(wrapper, label) {
  const b = wrapper.findAll("button").find((c) => c.text() === label);
  if (!b) throw new Error(`Unable to find button: ${label}`);
  return b;
}

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  }
  if (!Range.prototype.getClientRects) Range.prototype.getClientRects = () => [];
  if (!Range.prototype.getBoundingClientRect) {
    Range.prototype.getBoundingClientRect = () => ({
      bottom: 0, height: 0, left: 0, right: 0, top: 0, width: 0,
      x: 0, y: 0, toJSON: () => ({}),
    });
  }
  if (!Element.prototype.scrollTo) Element.prototype.scrollTo = () => {};
});

beforeEach(() => {
  window.localStorage.clear();
  setActivePinia(createPinia());
  serviceMocks.fetchSessionPracticeProblem.mockReset();
  serviceMocks.runSessionPractice.mockReset();
  serviceMocks.submitSessionPractice.mockReset();
});

afterEach(() => { vi.clearAllMocks(); });

// ── Quiz interaction ──────────────────────────────────────────────

describe("ResourceCanvas quiz interaction", () => {
  it("renders questions and options in expanded view, submits answers without a local score", async () => {
    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [quizCard("N01")],
        currentNode: "N01", nodeTitle: "Node 01", pathNodes: [],
        filterType: "quiz", loading: false,
        getCardLabel: () => "Diagnostic", getAgentLabel: () => "Evaluator",
        buildQuiz: () => [],
      },
    });
    await settleUi();

    expect(wrapper.text()).toContain("N01 question");
    expect(wrapper.text()).toContain("N01 option A");
    expect(wrapper.text()).toContain("N01 option B");

    // Submit disabled before answering
    expect(findButton(wrapper, "提交诊断").attributes("disabled")).toBeDefined();

    // Select an option
    await findButton(wrapper, "N01 option B").trigger("click");
    await settleUi();
    expect(findButton(wrapper, "提交诊断").attributes("disabled")).toBeUndefined();

    // Submit
    await findButton(wrapper, "提交诊断").trigger("click");
    await settleUi();

    const sub = wrapper.emitted("submit-quiz")[0][0];
    expect(sub).toMatchObject({ resourceId: "quiz-N01", attemptNumber: 1, usedHint: false });
    expect(sub.answers[0]).toMatchObject({ questionId: "question-N01", selectedOptionIndex: 1 });
    expect(sub).not.toHaveProperty("score");

    wrapper.unmount();
  });

  it("resets answers when switching nodes", async () => {
    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [quizCard("N01")],
        currentNode: "N01", nodeTitle: "Node 01", pathNodes: [],
        filterType: "quiz", loading: false,
        getCardLabel: () => "Diagnostic", getAgentLabel: () => "Evaluator",
        buildQuiz: () => [],
      },
    });
    await settleUi();

    await findButton(wrapper, "N01 option A").trigger("click");
    await settleUi();
    expect(findButton(wrapper, "提交诊断").attributes("disabled")).toBeUndefined();

    await wrapper.setProps({ currentNode: "N02", cards: [quizCard("N02")] });
    await settleUi();
    expect(wrapper.text()).toContain("N02 question");

    wrapper.unmount();
  });

  it("keeps quiz results open until returning or choosing the next chapter", async () => {
    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [quizCard("N01")],
        currentNode: "N01", nodeTitle: "Node 01",
        pathNodes: [
          { id: "N01", title: "Node 01", mastery: 0.4 },
          { id: "N02", title: "Node 02", mastery: 0 },
        ],
        filterType: "quiz", loading: false,
        getCardLabel: () => "Diagnostic", getAgentLabel: () => "Evaluator",
        buildQuiz: () => [],
      },
    });
    await settleUi();

    await findButton(wrapper, "N01 option A").trigger("click");
    await findButton(wrapper, "提交诊断").trigger("click");
    await settleUi();

    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    const firstSubmission = wrapper.emitted("submit-quiz")[0][0];
    firstSubmission.onRecorded({
      score: 0.5,
      evaluatedNodeId: "N01",
      nextNodeId: "N02",
      nextNodeTitle: "Node 02",
      questionResults: [{ prompt: "N01 question", correct: false }],
    });
    await settleUi();

    expect(document.body.querySelector('[role="dialog"]')?.textContent).toContain("诊断结果");
    document.body.querySelector(".quiz-result-btn--secondary").click();
    await settleUi();

    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    expect(findButton(wrapper, "提交诊断").attributes("disabled")).toBeUndefined();

    await findButton(wrapper, "提交诊断").trigger("click");
    wrapper.emitted("submit-quiz")[1][0].onRecorded({
      score: 1,
      evaluatedNodeId: "N01",
      nextNodeId: "N02",
      nextNodeTitle: "Node 02",
      advancedToNextNode: true,
      questionResults: [{ prompt: "N01 question", correct: true }],
    });
    await settleUi();
    const nextButton = [...document.body.querySelectorAll("button")]
      .find((button) => button.textContent === "下一章");
    nextButton.click();
    await settleUi();

    expect(wrapper.emitted("quiz-next")).toEqual([[{ nodeId: "N02" }]]);
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
    wrapper.unmount();
  });
});

// ── Card rendering ────────────────────────────────────────────────

describe("ResourceCanvas card rendering", () => {
  it("renders concept card with preview text", async () => {
    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [conceptCard("N01")],
        currentNode: "N01", nodeTitle: "Node 01", pathNodes: [],
        loading: false,
        getCardLabel: () => "Concept", getAgentLabel: () => "Agent",
        buildQuiz: () => [],
      },
    });
    await settleUi();
    expect(wrapper.text()).toContain("概念导图");
    expect(wrapper.text()).toContain("Concept summary");
    wrapper.unmount();
  });

  it("shows resource type filter tabs", async () => {
    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [conceptCard("N01"), quizCard("N01")],
        currentNode: "N01", nodeTitle: "Node 01", pathNodes: [],
        loading: false,
        getCardLabel: () => "Resource", getAgentLabel: () => "Agent",
        buildQuiz: () => [],
      },
    });
    await settleUi();
    expect(wrapper.text()).toContain("资源类型");
    expect(wrapper.text()).toContain("全部");
    wrapper.unmount();
  });

  it("emits filter-change on tab click", async () => {
    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [quizCard("N01")],
        currentNode: "N01", nodeTitle: "Node 01", pathNodes: [],
        filterType: "all", loading: false,
        getCardLabel: () => "Resource", getAgentLabel: () => "Agent",
        buildQuiz: () => [],
      },
    });
    await settleUi();

    const tab = wrapper.findAll("button").find((c) => c.text().includes("测验"));
    expect(tab).toBeTruthy();
    await tab.trigger("click");
    expect(wrapper.emitted("filter-change")[0][0]).toBe("quiz");

    wrapper.unmount();
  });

  it("shows preview without fabricated quiz options when payload is empty", async () => {
    const emptyQuiz = {
      resource_id: "empty-quiz", resource_type: "diagnostic_quiz",
      title: "Empty quiz", body_markdown: "", structured_payload: {},
    };
    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [emptyQuiz],
        currentNode: "N01", nodeTitle: "Node 01", pathNodes: [],
        loading: false,
        getCardLabel: () => "Diagnostic", getAgentLabel: () => "Evaluator",
        buildQuiz: () => [],
      },
    });
    await settleUi();

    expect(wrapper.text()).toContain("诊断测验");
    expect(wrapper.text()).not.toContain("与时间复杂度无关");
    expect(wrapper.text()).not.toContain("二分查找总是最优");
    expect(wrapper.text()).not.toContain("以上都不对");
    wrapper.unmount();
  });
});

// ── CodePracticePanel ─────────────────────────────────────────────

describe("CodePracticePanel request snapshots", () => {
  it("restores final local edit after logout instead of older server draft", async () => {
    const sid = "learner:course-draft";
    serviceMocks.fetchSessionPracticeProblem.mockResolvedValue({
      id: "p1", version: "v1", title: "Draft", language: "python",
      starter_code: "print('s')", public_test_count: 1, hidden_test_count: 1,
    });
    const assets = useLearningAssetsStore();
    assets.setSession(sid);

    const w = mount(CodePracticePanel, {
      props: { sessionId: sid, nodeId: "N01", resourceId: "r1", problemId: "p1", starterCode: "print('s')", language: "python" },
    });
    await settleUi();

    const ed = EditorView.findFromDOM(w.get(".cm-content").element);
    ed.dispatch({ changes: { from: 0, to: ed.state.doc.length, insert: "print('Z')" } });
    assets.reset();
    w.unmount();

    const prefix = `eduagent:practice-draft:v2:${sid}:`;
    const key = Object.keys(localStorage).find((k) => k.startsWith(prefix));
    const draft = JSON.parse(localStorage.getItem(key));
    expect(draft.code).toBe("print('Z')");

    assets.setSession(sid);
    assets.write("code_drafts", key.slice(prefix.length), { ...draft, code: "old", updated_at: draft.updated_at - 60_000 }, { sync: false });

    const w2 = mount(CodePracticePanel, {
      props: { sessionId: sid, nodeId: "N01", resourceId: "r1", problemId: "p1", starterCode: "print('s')", language: "python" },
    });
    await settleUi();
    expect(EditorView.findFromDOM(w2.get(".cm-content").element).state.doc.toString()).toBe("print('Z')");
    w2.unmount();
  });

  it("attributes overlapping node runs to request-time context", async () => {
    const runA = deferred(); const runB = deferred();
    serviceMocks.fetchSessionPracticeProblem.mockImplementation(async (_s, rid) => ({
      id: rid, title: `${rid}`, language: "python", starter_code: `print('${rid}')`, public_test_count: 1, hidden_test_count: 1,
    }));
    serviceMocks.runSessionPractice.mockImplementation((_s, p) => p.resource_id === "rA" ? runA.promise : runB.promise);

    useLearningAssetsStore().setSession("learner:course");
    const w = mount(CodePracticePanel, {
      props: { sessionId: "learner:course", nodeId: "N01", resourceId: "rA", problemId: "rA", starterCode: "print('rA')", language: "python" },
    });
    await settleUi();

    await findButton(w, "运行公开测试").trigger("click");
    await w.setProps({ nodeId: "N02", resourceId: "rB", problemId: "rB", starterCode: "print('rB')" });
    await settleUi();
    await findButton(w, "运行公开测试").trigger("click");

    runA.resolve({ status: "ok", mode: "run", verdict: "wrong_answer", resource_id: "rA" });
    await settleUi();
    expect(w.emitted("code-run")[0][0]).toMatchObject({ nodeId: "N01", resourceId: "rA", codeSnapshot: "print('rA')" });
    expect(findButton(w, "运行中...").attributes("disabled")).toBeDefined();
    expect(w.text()).not.toContain("答案错误");

    runB.resolve({ status: "ok", mode: "run", verdict: "accepted", resource_id: "rB" });
    await settleUi();
    expect(w.emitted("code-run")[1][0]).toMatchObject({ nodeId: "N02", resourceId: "rB", codeSnapshot: "print('rB')" });
    expect(w.text()).toContain("通过");

    w.unmount();
  });
});
