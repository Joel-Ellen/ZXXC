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
import ConceptMapLearning from "./ConceptMapLearning.vue";
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

function codeCard(nodeId) {
  return {
    resource_id: `code-${nodeId}`,
    resource_type: "code_snippet",
    title: `${nodeId} code`,
    structured_payload: {
      language: "c",
      scenario: "Read the first array value safely.",
      code: "int first_value(const int *values, size_t count) { return count ? values[0] : 0; }",
      practice: {
        problem_id: "arrays-first-value",
        language: "c",
        starter_code: "int first_value(const int *values, size_t count) { (void)values; (void)count; return 0; }",
      },
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
      masteryBefore: 0.3,
      masteryAfter: 0.45,
      evaluatedNodeId: "N01",
      nextNodeId: "N02",
      nextNodeTitle: "Node 02",
      questionResults: [{
        prompt: "N01 question",
        correct: false,
        selected_answer: "N01 option A",
        correct_answer: "N01 option B",
        explanation: "Check the governing condition.",
      }],
    });
    await settleUi();

    const resultText = document.body.querySelector('[role="dialog"]')?.textContent;
    expect(resultText).toContain("诊断结果");
    expect(resultText).toContain("需要复习");
    expect(resultText).toContain("提升 15%");
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

  it("renders a Mermaid container for legacy concept markdown", async () => {
    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [{
          resource_id: "legacy-concept",
          resource_type: "concept_map",
          title: "Legacy concept",
          body_markdown: "## Legacy concept\n\n```mermaid\ngraph TD\nA[Start] --> B[End]\n```",
          structured_payload: {},
        }],
        currentNode: "N01", nodeTitle: "Node 01", pathNodes: [],
        filterType: "concept", loading: false,
        getCardLabel: () => "Concept", getAgentLabel: () => "Agent",
        buildQuiz: () => [],
      },
    });
    await settleUi();

    expect(wrapper.find(".mermaid-canvas").exists()).toBe(true);
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

  it("mounts the C practice panel in code details and forwards run events", async () => {
    const starter = "int first_value(const int *values, size_t count) { (void)values; (void)count; return 0; }";
    serviceMocks.fetchSessionPracticeProblem.mockResolvedValue({
      id: "arrays-first-value",
      version: "v2",
      title: "Array first value",
      language: "c",
      starter_code: starter,
      public_test_count: 1,
      hidden_test_count: 1,
    });
    serviceMocks.runSessionPractice.mockResolvedValue({
      status: "ok",
      mode: "run",
      verdict: "accepted",
      resource_id: "code-N01",
    });

    const wrapper = mount(ResourceCanvas, {
      props: {
        sessionId: "learner:course",
        cards: [codeCard("N01")],
        currentNode: "N01",
        nodeTitle: "Node 01",
        pathNodes: [],
        filterType: "code",
        loading: false,
        getCardLabel: () => "Code",
        getAgentLabel: () => "Agent",
        buildQuiz: () => [],
      },
    });
    await settleUi();

    const panel = wrapper.findComponent(CodePracticePanel);
    expect(panel.exists()).toBe(true);
    expect(panel.props()).toMatchObject({
      sessionId: "learner:course",
      nodeId: "N01",
      resourceId: "code-N01",
      problemId: "arrays-first-value",
      language: "c",
    });
    expect(serviceMocks.fetchSessionPracticeProblem)
      .toHaveBeenCalledWith("learner:course", "arrays-first-value");

    await panel.find(".code-practice-panel__actions button").trigger("click");
    await settleUi();

    expect(serviceMocks.runSessionPractice).toHaveBeenCalledWith(
      "learner:course",
      { resource_id: "code-N01", language: "c", code: starter },
    );
    expect(wrapper.emitted("code-run")?.[0]?.[0]).toMatchObject({
      sessionId: "learner:course",
      nodeId: "N01",
      resourceId: "code-N01",
      problemId: "arrays-first-value",
      codeSnapshot: starter,
    });
    wrapper.unmount();
  });

  it("does not request a practice problem for an unbound legacy code card", async () => {
    const legacyCard = codeCard("N01");
    delete legacyCard.structured_payload.practice;
    const wrapper = mount(ResourceCanvas, {
      props: {
        sessionId: "learner:course",
        cards: [legacyCard],
        currentNode: "N01",
        nodeTitle: "Node 01",
        pathNodes: [],
        filterType: "code",
        loading: false,
        getCardLabel: () => "Code",
        getAgentLabel: () => "Agent",
        buildQuiz: () => [],
      },
    });
    await settleUi();

    expect(wrapper.findComponent(CodePracticePanel).exists()).toBe(false);
    expect(serviceMocks.fetchSessionPracticeProblem).not.toHaveBeenCalled();
    wrapper.unmount();
  });
});

describe("ConceptMapLearning", () => {
  it("turns structured concept fields into a branching learning map", async () => {
    const wrapper = mount(ConceptMapLearning, {
      props: { card: conceptCard("N01"), nodeTitle: "Node 01" },
    });
    await settleUi();

    expect(wrapper.text()).toContain("一句话定义");
    expect(wrapper.text()).toContain("前置基础");
    expect(wrapper.text()).toContain("成立条件");
    expect(wrapper.text()).toContain("边界与反例");
    expect(wrapper.text()).toContain("迁移挑战");
    expect(wrapper.findAll("button").length).toBeGreaterThan(5);

    const mechanism = wrapper.find("button[aria-label='通过：mechanism step']");
    expect(mechanism.exists()).toBe(true);
    await mechanism.trigger("click");
    expect(wrapper.find(".concept-map__detail").text()).toContain("mechanism step");

    const outlineTab = wrapper.findAll("button[role='tab']").find((button) => button.text() === "学习提纲");
    expect(outlineTab).toBeTruthy();
    await outlineTab.trigger("click");
    expect(wrapper.find("[role='tabpanel']").text()).toContain("学习目标");
    wrapper.unmount();
  });

  it("keeps a useful scaffold for legacy cards without structured fields", async () => {
    const wrapper = mount(ConceptMapLearning, {
      props: {
        card: {
          resource_id: "legacy-concept",
          resource_type: "concept_map",
          title: "旧概念",
          body_markdown: "## 旧概念\n\n这是历史卡片中的中文摘要。",
          structured_payload: {},
        },
      },
    });
    await settleUi();

    expect(wrapper.text()).toContain("旧概念");
    expect(wrapper.text()).toContain("先确认该节点依赖的基础概念");
    expect(wrapper.text()).toContain("迁移挑战");
    expect(wrapper.text()).not.toContain("关系节点\n1");
    wrapper.unmount();
  });
});

// ── CodePracticePanel ─────────────────────────────────────────────

describe("CodePracticePanel request snapshots", () => {
  it("does not restore an explicit Python draft into the C editor", async () => {
    const sid = "learner:course-language";
    const starter = "int sum_values(const int *values, size_t count) { (void)values; (void)count; return 0; }";
    serviceMocks.fetchSessionPracticeProblem.mockResolvedValue({
      id: "p-c",
      version: "v2",
      title: "C draft",
      language: "c",
      starter_code: starter,
      public_test_count: 1,
      hidden_test_count: 1,
    });
    window.localStorage.setItem(
      `eduagent:practice-draft:v1:${sid}:r-c`,
      JSON.stringify({
        resource_id: "r-c",
        problem_id: "p-c",
        version: "v2",
        language: "python",
        code: "def sum_values(values):\n    return sum(values)",
        updated_at: Date.now(),
      }),
    );

    const wrapper = mount(CodePracticePanel, {
      props: {
        sessionId: sid,
        nodeId: "N01",
        resourceId: "r-c",
        problemId: "p-c",
        language: "c",
      },
    });
    await settleUi();

    expect(EditorView.findFromDOM(wrapper.get(".cm-content").element).state.doc.toString())
      .toBe(starter);
    wrapper.unmount();
  });

  it("does not migrate a language-less legacy draft into the C editor", async () => {
    const sid = "learner:course-language-less";
    const starter = "int sum_values(const int *values, size_t count) { (void)values; (void)count; return 0; }";
    serviceMocks.fetchSessionPracticeProblem.mockResolvedValue({
      id: "p-c",
      version: "v2",
      title: "C draft",
      language: "c",
      starter_code: starter,
      public_test_count: 1,
      hidden_test_count: 1,
    });
    window.localStorage.setItem(
      `eduagent:practice-draft:v1:${sid}:r-c`,
      JSON.stringify({
        resource_id: "r-c",
        problem_id: "p-c",
        version: "v2",
        code: "def sum_values(values):\n    return sum(values)",
        updated_at: Date.now(),
      }),
    );

    const wrapper = mount(CodePracticePanel, {
      props: {
        sessionId: sid,
        nodeId: "N01",
        resourceId: "r-c",
        problemId: "p-c",
        language: "c",
      },
    });
    await settleUi();

    expect(EditorView.findFromDOM(wrapper.get(".cm-content").element).state.doc.toString())
      .toBe(starter);
    wrapper.unmount();
  });

  it("does not invent a main function when the server omits a starter template", async () => {
    serviceMocks.fetchSessionPracticeProblem.mockResolvedValue({
      id: "missing-template",
      version: "v2",
      title: "Missing template",
      language: "c",
      public_test_count: 1,
      hidden_test_count: 1,
    });

    const wrapper = mount(CodePracticePanel, {
      props: {
        sessionId: "learner:course-missing-template",
        nodeId: "N01",
        resourceId: "r-missing-template",
        problemId: "missing-template",
        language: "c",
      },
    });
    await settleUi();

    expect(wrapper.find(".cm-content").exists()).toBe(false);
    expect(wrapper.text()).toContain("缺少服务端提供的 C 函数模板");
    expect(wrapper.text()).not.toContain("int main(void)");
    wrapper.unmount();
  });

  it("restores final local edit after logout instead of older server draft", async () => {
    const sid = "learner:course-draft";
    serviceMocks.fetchSessionPracticeProblem.mockResolvedValue({
      id: "p1", version: "v1", title: "Draft", language: "c",
      starter_code: "int solve(void) { return 0; }", public_test_count: 1, hidden_test_count: 1,
    });
    const assets = useLearningAssetsStore();
    assets.setSession(sid);

    const w = mount(CodePracticePanel, {
      props: { sessionId: sid, nodeId: "N01", resourceId: "r1", problemId: "p1", starterCode: "int solve(void) { return 0; }", language: "c" },
    });
    await settleUi();

    const ed = EditorView.findFromDOM(w.get(".cm-content").element);
    ed.dispatch({ changes: { from: 0, to: ed.state.doc.length, insert: "int value = 42;" } });
    assets.reset();
    w.unmount();

    const prefix = `eduagent:practice-draft:v2:${sid}:`;
    const key = Object.keys(localStorage).find((k) => k.startsWith(prefix));
    const draft = JSON.parse(localStorage.getItem(key));
    expect(draft.code).toBe("int value = 42;");

    assets.setSession(sid);
    assets.write("code_drafts", key.slice(prefix.length), { ...draft, code: "old", updated_at: draft.updated_at - 60_000 }, { sync: false });

    const w2 = mount(CodePracticePanel, {
      props: { sessionId: sid, nodeId: "N01", resourceId: "r1", problemId: "p1", starterCode: "int solve(void) { return 0; }", language: "c" },
    });
    await settleUi();
    expect(EditorView.findFromDOM(w2.get(".cm-content").element).state.doc.toString()).toBe("int value = 42;");
    w2.unmount();
  });

  it("attributes overlapping node runs to request-time context", async () => {
    const runA = deferred(); const runB = deferred();
    serviceMocks.fetchSessionPracticeProblem.mockImplementation(async (_s, rid) => ({
      id: rid, title: `${rid}`, language: "c", starter_code: `int ${rid === "rA" ? "first" : "second"} = 1;`, public_test_count: 1, hidden_test_count: 1,
    }));
    serviceMocks.runSessionPractice.mockImplementation((_s, p) => p.resource_id === "rA" ? runA.promise : runB.promise);

    useLearningAssetsStore().setSession("learner:course");
    const w = mount(CodePracticePanel, {
      props: { sessionId: "learner:course", nodeId: "N01", resourceId: "rA", problemId: "rA", starterCode: "int first = 1;", language: "c" },
    });
    await settleUi();

    await findButton(w, "运行公开测试").trigger("click");
    expect(serviceMocks.runSessionPractice).toHaveBeenCalledWith(
      "learner:course",
      expect.objectContaining({ language: "c", code: "int first = 1;" }),
    );
    await w.setProps({ nodeId: "N02", resourceId: "rB", problemId: "rB", starterCode: "int second = 1;" });
    await settleUi();
    await findButton(w, "运行公开测试").trigger("click");

    runA.resolve({ status: "ok", mode: "run", verdict: "wrong_answer", resource_id: "rA" });
    await settleUi();
    expect(w.emitted("code-run")[0][0]).toMatchObject({ nodeId: "N01", resourceId: "rA", codeSnapshot: "int first = 1;" });
    expect(findButton(w, "运行中...").attributes("disabled")).toBeDefined();
    expect(w.text()).not.toContain("答案错误");

    runB.resolve({ status: "ok", mode: "run", verdict: "accepted", resource_id: "rB" });
    await settleUi();
    expect(w.emitted("code-run")[1][0]).toMatchObject({ nodeId: "N02", resourceId: "rB", codeSnapshot: "int second = 1;" });
    expect(w.text()).toContain("通过");

    w.unmount();
  });
});
