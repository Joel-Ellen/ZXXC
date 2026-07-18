import { describe, expect, it } from "vitest";
import { normalizeLearningEvent } from "./learning";
import {
  normalizePracticeExecutionRequest,
  normalizePracticeExecutionResponse,
} from "./practice";
import { normalizeTutorRequest } from "./tutor";

describe("learning contracts", () => {
  it("normalizes canonical fields without accepting client mastery claims", () => {
    const event = normalizeLearningEvent({
      eventType: "lesson-completed",
      eventId: " event-1 ",
      userId: " learner-1 ",
      courseId: " course-1 ",
      nodeId: " node-1 ",
      resourceId: " resource-1 ",
      durationMs: 1250,
      attemptNumber: 2,
      usedHint: true,
      result: { passed: true, score: 1, correctness: 1, mastery_score: 1, mastery_delta: 0.7 },
      completionEvidence: {
        evidenceType: "diagnostic_quiz",
        resourceId: "resource-1",
        answers: [{ questionId: "q-1", selectedOptionIndex: 2 }],
      },
    });

    expect(event).toMatchObject({
      event_id: "event-1",
      event_type: "lesson_completed",
      duration_ms: 1250,
      attempt_number: 2,
      used_hint: true,
      result: { passed: true },
      completion_evidence: {
        answers: [{ question_id: "q-1", answer_index: 2 }],
      },
    });
    expect(event.result).not.toHaveProperty("mastery_score");
    expect(event.result).not.toHaveProperty("mastery_delta");
    expect(event.result).not.toHaveProperty("score");
    expect(event.result).not.toHaveProperty("correctness");
  });

  it("rejects events outside the stable vocabulary", () => {
    expect(() => normalizeLearningEvent({ event_type: "browse_node" }))
      .toThrow("Unsupported learning event type");
  });

  it("rejects fabricated or malformed timing counters", () => {
    expect(() => normalizeLearningEvent({ event_type: "content_viewed", duration_ms: -1 }))
      .toThrow("duration_ms must be an integer");
    expect(() => normalizeLearningEvent({ event_type: "answer_submitted", attempt_number: 1.5 }))
      .toThrow("attempt_number must be an integer");
  });
});

describe("Tutor contracts", () => {
  it("preserves real debug context from camel-case UI fields", () => {
    expect(normalizeTutorRequest({
      question: " Why does this fail? ",
      contextType: "debug",
      codeSnippet: " print(value) ",
      errorMessage: " NameError ",
      stream: true,
    })).toEqual({
      question: "Why does this fail?",
      context_type: "code_debug",
      code_snippet: "print(value)",
      error_message: "NameError",
      stream: true,
    });
  });

  it("rejects blank questions and unknown contexts", () => {
    expect(() => normalizeTutorRequest({ question: "" })).toThrow("Tutor question is required");
    expect(() => normalizeTutorRequest({ question: "help", contextType: "fictional" }))
      .toThrow("Unsupported tutor context type");
  });
});

describe("practice contracts", () => {
  it("normalizes a server-bound run request", () => {
    expect(normalizePracticeExecutionRequest({
      resourceId: " resource-1 ",
      problemId: " problem-1 ",
      sourceCode: " def solve():\n    return 1 ",
      language: "PYTHON",
      mode: "run",
    })).toEqual({
      resource_id: "resource-1",
      problem_id: "problem-1",
      source_code: " def solve():\n    return 1 ",
      language: "python",
      mode: "run",
    });
  });

  it("normalizes verdicts while suppressing hidden test values", () => {
    const response = normalizePracticeExecutionResponse({
      status: "ok",
      mode: "submit",
      resource_id: "resource-1",
      node_id: "node-1",
      problem_id: "problem-1",
      problem_version: "v2",
      verdict: "wrong_answer",
      tests: [
        { id: "public-1", visibility: "public", passed: true, verdict: "accepted", input: [1], expected: 1, actual: 1 },
        { id: "hidden-1", visibility: "hidden", passed: false, verdict: "wrong_answer", input: [99], expected: 100, actual: 99 },
      ],
      runtime_ms: 8.5,
      memory_kb: 2048,
      summary: { public_passed: 1, public_total: 1, hidden_passed: 0, hidden_total: 1, passed: 1, total: 2 },
      submission_id: "receipt-1",
    });

    expect(response.status).toBe("ok");
    if (response.status !== "ok") throw new Error("Expected an execution result");
    expect(response.verdict).toBe("wrong_answer");
    expect(response.submission_id).toBe("receipt-1");
    expect(response.tests[0]).toMatchObject({ input: [1], expected: 1, actual: 1 });
    expect(response.tests[1]).not.toHaveProperty("input");
    expect(response.tests[1]).not.toHaveProperty("expected");
    expect(response.tests[1]).not.toHaveProperty("actual");
  });
});
