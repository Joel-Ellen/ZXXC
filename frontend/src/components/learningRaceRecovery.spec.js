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
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function settleUi() {
  await Promise.resolve();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
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
        explanation: "Verified explanation",
      }],
    },
  };
}

function practiceCard(nodeId) {
  return {
    resource_id: `${nodeId}_interactive_exercise_supp`,
    resource_type: "interactive_exercise",
    title: `${nodeId} targeted practice`,
    structured_payload: {
      goal: "Check the key constraint",
      prompt: "Apply the concept before the retest.",
      questions: [{
        id: `${nodeId}-targeted-practice-q1-v1`,
        prompt: "Which method checks the constraint?",
        options: ["Ignore the boundary", "Apply and check the boundary"],
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
      objectives: [],
    },
  };
}

function findButton(wrapper, label) {
  const button = wrapper.findAll("button").find((candidate) => candidate.text() === label);
  if (!button) throw new Error(`Unable to find button: ${label}`);
  return button;
}

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  if (!Range.prototype.getClientRects) {
    Range.prototype.getClientRects = () => [];
  }
  if (!Range.prototype.getBoundingClientRect) {
    Range.prototype.getBoundingClientRect = () => ({
      bottom: 0,
      height: 0,
      left: 0,
      right: 0,
      top: 0,
      width: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
  }
});

beforeEach(() => {
  window.localStorage.clear();
  setActivePinia(createPinia());
  serviceMocks.fetchSessionPracticeProblem.mockReset();
  serviceMocks.runSessionPractice.mockReset();
  serviceMocks.submitSessionPractice.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("ResourceCanvas route recovery", () => {
  it("restores answers, per-question receipts, and the next attempt after Back", async () => {
    const assets = useLearningAssetsStore();
    assets.setSession("learner:course");
    const n01Card = quizCard("N01");
    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [n01Card],
        sessionId: "learner:course",
        currentNode: "N01",
        nodeTitle: "Node 01",
        pathNodes: [],
        getCardLabel: () => "Diagnostic",
        getAgentLabel: () => "Evaluator",
        buildQuiz: () => null,
      },
    });
    await settleUi();

    await findButton(wrapper, "N01 option B").trigger("click");
    await findButton(wrapper, "Submit answer").trigger("click");
    const answerSubmission = wrapper.emitted("submit-quiz").at(-1)[0];
    expect(answerSubmission).toMatchObject({
      eventKind: "answer_submitted",
      nodeId: "N01",
      resourceId: "quiz-N01",
      attemptNumber: 1,
    });
    answerSubmission.onRecorded();
    await settleUi();
    expect(wrapper.text()).toContain("Answer saved");

    await findButton(wrapper, "提交诊断").trigger("click");
    const completion = wrapper.emitted("submit-quiz").at(-1)[0];
    expect(completion.attemptNumber).toBe(1);
    completion.onFailure(new Error("response lost"));
    await settleUi();

    await findButton(wrapper, "重新提交诊断").trigger("click");
    const completionRetry = wrapper.emitted("submit-quiz").at(-1)[0];
    expect(completionRetry.eventId).toBe(completion.eventId);
    expect(completionRetry.attemptNumber).toBe(1);
    completionRetry.onRecorded();
    await settleUi();

    await wrapper.setProps({ currentNode: "N02", cards: [quizCard("N02")] });
    await settleUi();
    expect(wrapper.text()).toContain("N02 question");

    await wrapper.setProps({ currentNode: "N01", cards: [n01Card] });
    await settleUi();
    expect(wrapper.text()).toContain("Answer saved");
    expect(findButton(wrapper, "N01 option B").classes()).toContain("bg-primary-soft");

    await findButton(wrapper, "提交诊断").trigger("click");
    const retriedCompletion = wrapper.emitted("submit-quiz").at(-1)[0];
    expect(retriedCompletion.attemptNumber).toBe(2);
    expect(retriedCompletion.nodeId).toBe("N01");

    wrapper.unmount();
  });

  it("restores used_hint from durable quiz progress before completion", async () => {
    const assets = useLearningAssetsStore();
    assets.setSession("learner:course");
    assets.write("quiz_progress", "quiz:N01:quiz-N01", {
      node_id: "N01",
      resource_id: "quiz-N01",
      attempt_number: 2,
      answers: { "question-N01": 1 },
      submitted_question_ids: ["question-N01"],
      used_hint: true,
    }, { sync: false });

    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [quizCard("N01")],
        sessionId: "learner:course",
        currentNode: "N01",
        nodeTitle: "Node 01",
        pathNodes: [],
        getCardLabel: () => "Diagnostic",
        getAgentLabel: () => "Evaluator",
        buildQuiz: () => null,
      },
    });
    await settleUi();

    await findButton(wrapper, "提交诊断").trigger("click");
    const completion = wrapper.emitted("submit-quiz").at(-1)[0];
    expect(completion).toMatchObject({
      resourceId: "quiz-N01",
      attemptNumber: 2,
      usedHint: true,
    });
    wrapper.unmount();
  });

  it("requires a submitted targeted-practice answer and reuses its event on retry", async () => {
    const assets = useLearningAssetsStore();
    assets.setSession("learner:course");
    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [practiceCard("N01")],
        sessionId: "learner:course",
        currentNode: "N01",
        nodeTitle: "Node 01",
        pathNodes: [],
        reviewItemId: "review-1",
        reviewPhase: "material_review",
        getCardLabel: () => "Practice",
        getAgentLabel: () => "Coach",
        buildQuiz: () => null,
      },
    });
    await settleUi();

    expect(findButton(wrapper, "提交练习并生成复测").attributes("disabled")).toBeDefined();
    await wrapper.find('input[type="radio"][value="1"]').setValue(true);
    await findButton(wrapper, "提交练习并生成复测").trigger("click");
    const first = wrapper.emitted("prepare-review-retest").at(-1)[0];
    expect(first).toMatchObject({
      reviewItemId: "review-1",
      resourceId: "N01_interactive_exercise_supp",
      questionId: "N01-targeted-practice-q1-v1",
      selectedOptionIndex: 1,
      attemptNumber: 1,
      practiceEventId: "",
    });
    first.onPracticeRecorded("practice-event-1");
    first.onFailure(new Error("response lost"));
    await settleUi();

    await findButton(wrapper, "重试生成复测").trigger("click");
    const retry = wrapper.emitted("prepare-review-retest").at(-1)[0];
    expect(retry.practiceEventId).toBe("practice-event-1");
    wrapper.unmount();
  });

  it("restores and updates the active card through synchronized card_state", async () => {
    const assets = useLearningAssetsStore();
    assets.setSession("learner:course");
    assets.write("card_state", "canvas:N01", {
      node_id: "N01",
      resource_id: "quiz-N01",
      card_id: "quiz-N01",
      expanded: true,
    }, { sync: false });

    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [practiceCard("N01"), quizCard("N01")],
        sessionId: "learner:course",
        currentNode: "N01",
        nodeTitle: "Node 01",
        pathNodes: [],
        getCardLabel: () => "Resource",
        getAgentLabel: () => "Agent",
        buildQuiz: () => null,
      },
    });
    await settleUi();

    expect(wrapper.find('[data-resource-id="quiz-N01"]').classes()).toContain("is-active");
    await findButton(wrapper, "练习").trigger("click");
    expect(assets.read("card_state", "canvas:N01")).toMatchObject({
      node_id: "N01",
      resource_id: "N01_interactive_exercise_supp",
      card_id: "N01_interactive_exercise_supp",
      expanded: true,
    });
    wrapper.unmount();
  });

  it("keeps the active card while later resource cards arrive", async () => {
    const wrapper = mount(ResourceCanvas, {
      props: {
        cards: [conceptCard("N01"), quizCard("N01")],
        cardStates: {
          concept_map: { status: "ready" },
          diagnostic_quiz: { status: "ready" },
          code_snippet: { status: "waiting" },
          interactive_exercise: { status: "waiting" },
          video_summary: { status: "waiting" },
        },
        sessionId: "learner:course",
        currentNode: "N01",
        nodeTitle: "Node 01",
        pathNodes: [],
        getCardLabel: (type) => type,
        getAgentLabel: () => "Agent",
        buildQuiz: () => [],
      },
    });
    await settleUi();

    await findButton(wrapper, "反馈").trigger("click");
    await settleUi();
    expect(wrapper.find('[data-resource-id="quiz-N01"]').classes()).toContain("is-active");

    await wrapper.setProps({
      cards: [conceptCard("N01"), quizCard("N01"), practiceCard("N01")],
      cardStates: {
        concept_map: { status: "ready" },
        diagnostic_quiz: { status: "ready" },
        interactive_exercise: { status: "ready" },
        code_snippet: { status: "waiting" },
        video_summary: { status: "waiting" },
      },
    });
    await settleUi();

    expect(wrapper.find('[data-resource-id="quiz-N01"]').classes()).toContain("is-active");
    expect(wrapper.findAll('[data-resource-type]').map((element) => element.attributes("data-resource-type"))).toEqual([
      "concept_map",
      "code_snippet",
      "interactive_exercise",
      "video_summary",
      "diagnostic_quiz",
    ]);
    wrapper.unmount();
  });
});

describe("CodePracticePanel request snapshots", () => {
  it("restores the final local edit after immediate logout instead of an older synchronized draft", async () => {
    const sessionId = "learner:course-draft";
    serviceMocks.fetchSessionPracticeProblem.mockResolvedValue({
      id: "problem-draft",
      version: "v1",
      title: "Draft recovery",
      language: "python",
      starter_code: "print('starter')",
      public_test_count: 1,
      hidden_test_count: 1,
    });

    const assets = useLearningAssetsStore();
    assets.setSession(sessionId);
    const wrapper = mount(CodePracticePanel, {
      props: {
        sessionId,
        nodeId: "N01",
        resourceId: "resource-draft",
        problemId: "problem-draft",
        starterCode: "print('starter')",
        language: "python",
      },
    });
    await settleUi();

    const editor = EditorView.findFromDOM(wrapper.get(".cm-content").element);
    expect(editor).not.toBeNull();
    editor.dispatch({
      changes: {
        from: 0,
        to: editor.state.doc.length,
        insert: "print('local final Z')",
      },
    });

    assets.reset();
    wrapper.unmount();

    const storagePrefix = `eduagent:practice-draft:v2:${sessionId}:`;
    const localKey = Object.keys(window.localStorage).find((key) => key.startsWith(storagePrefix));
    expect(localKey).toBeTruthy();
    const localDraft = JSON.parse(window.localStorage.getItem(localKey));
    expect(localDraft.code).toBe("print('local final Z')");

    const assetKey = localKey.slice(storagePrefix.length);
    assets.setSession(sessionId);
    assets.write("code_drafts", assetKey, {
      ...localDraft,
      code: "print('older server draft')",
      updated_at: localDraft.updated_at - 60_000,
    }, { sync: false });

    const restored = mount(CodePracticePanel, {
      props: {
        sessionId,
        nodeId: "N01",
        resourceId: "resource-draft",
        problemId: "problem-draft",
        starterCode: "print('starter')",
        language: "python",
      },
    });
    await settleUi();

    const restoredEditor = EditorView.findFromDOM(restored.get(".cm-content").element);
    expect(restoredEditor.state.doc.toString()).toBe("print('local final Z')");
    restored.unmount();
  });

  it("keeps overlapping node results attributed to their request-time context", async () => {
    const runA = deferred();
    const runB = deferred();
    serviceMocks.fetchSessionPracticeProblem.mockImplementation(async (sessionId, resourceId) => ({
      id: resourceId,
      title: `${resourceId} practice`,
      language: "python",
      starter_code: `print('${resourceId}')`,
      public_test_count: 1,
      hidden_test_count: 1,
    }));
    serviceMocks.runSessionPractice.mockImplementation((sessionId, payload) => (
      payload.resource_id === "resource-A" ? runA.promise : runB.promise
    ));

    const assets = useLearningAssetsStore();
    assets.setSession("learner:course");
    const wrapper = mount(CodePracticePanel, {
      props: {
        sessionId: "learner:course",
        nodeId: "N01",
        resourceId: "resource-A",
        problemId: "resource-A",
        starterCode: "print('resource-A')",
        language: "python",
      },
    });
    await settleUi();

    await findButton(wrapper, "运行公开测试").trigger("click");
    await wrapper.setProps({
      nodeId: "N02",
      resourceId: "resource-B",
      problemId: "resource-B",
      starterCode: "print('resource-B')",
    });
    await settleUi();
    await findButton(wrapper, "运行公开测试").trigger("click");

    runA.resolve({ status: "ok", mode: "run", verdict: "wrong_answer", resource_id: "resource-A" });
    await settleUi();
    const eventA = wrapper.emitted("code-run")[0][0];
    expect(eventA).toMatchObject({
      sessionId: "learner:course",
      nodeId: "N01",
      resourceId: "resource-A",
      attemptNumber: 1,
      codeSnapshot: "print('resource-A')",
    });
    expect(findButton(wrapper, "运行中...").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).not.toContain("答案错误");

    runB.resolve({ status: "ok", mode: "run", verdict: "accepted", resource_id: "resource-B" });
    await settleUi();
    const eventB = wrapper.emitted("code-run")[1][0];
    expect(eventB).toMatchObject({
      sessionId: "learner:course",
      nodeId: "N02",
      resourceId: "resource-B",
      attemptNumber: 1,
      codeSnapshot: "print('resource-B')",
    });
    expect(wrapper.text()).toContain("通过");

    wrapper.unmount();
  });
});
