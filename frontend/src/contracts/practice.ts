import { asRecord, boundedInteger, boundedNumber, normalizedString, readAlias } from "./runtime";
import type { UnknownRecord } from "./runtime";

export const PRACTICE_VERDICTS = [
  "accepted",
  "wrong_answer",
  "syntax_error",
  "runtime_error",
  "time_limit",
  "internal_error",
] as const;

export type PracticeMode = "run" | "submit";
export type PracticeVerdict = typeof PRACTICE_VERDICTS[number];
export type TestVisibility = "public" | "hidden";

export interface PracticeExecutionRequest {
  resource_id: string;
  problem_id: string;
  language: "python";
  source_code: string;
  mode: PracticeMode;
}

export interface PracticeTestResult {
  id: string;
  visibility: TestVisibility;
  passed: boolean;
  verdict: PracticeVerdict;
  input?: unknown;
  expected?: unknown;
  actual?: unknown;
  message?: string;
}

export interface PracticeSummary {
  public_passed: number;
  public_total: number;
  hidden_passed: number;
  hidden_total: number;
  passed: number;
  total: number;
}

export interface PracticeExecutionSuccess {
  status: "ok";
  mode: PracticeMode;
  resource_id: string;
  node_id: string;
  problem_id: string;
  problem_version: string;
  verdict: PracticeVerdict;
  tests: PracticeTestResult[];
  summary: PracticeSummary;
  runtime_ms: number;
  memory_kb: number | null;
  message: string;
  submission_id?: string;
}

export interface PracticeExecutionFailure {
  status: "error";
  code: string;
  message: string;
  details: Readonly<UnknownRecord>;
}

export type PracticeExecutionResponse = PracticeExecutionSuccess | PracticeExecutionFailure;

const VERDICT_SET = new Set<string>(PRACTICE_VERDICTS);

function normalizedMode(value: unknown): PracticeMode {
  const mode = normalizedString(value).toLowerCase();
  if (mode !== "run" && mode !== "submit") {
    throw new TypeError(`Unsupported practice mode: ${mode || "<empty>"}`);
  }
  return mode;
}

function normalizedVerdict(value: unknown): PracticeVerdict {
  const verdict = normalizedString(value).toLowerCase();
  return VERDICT_SET.has(verdict) ? verdict as PracticeVerdict : "internal_error";
}

export function normalizePracticeExecutionRequest(value: unknown): PracticeExecutionRequest {
  const source = asRecord(value);
  const resourceId = normalizedString(readAlias(source, "resource_id", "resourceId"));
  const rawSourceCode = readAlias(source, "source_code", "sourceCode", "code");
  const sourceCode = typeof rawSourceCode === "string" ? rawSourceCode : "";
  if (!resourceId) throw new TypeError("Practice resource_id is required");
  if (!sourceCode.trim()) throw new TypeError("Practice source_code is required");

  const language = normalizedString(source.language).toLowerCase() || "python";
  if (language !== "python") throw new TypeError(`Unsupported practice language: ${language}`);

  return {
    resource_id: resourceId,
    problem_id: normalizedString(readAlias(source, "problem_id", "problemId")),
    language,
    source_code: sourceCode,
    mode: normalizedMode(source.mode),
  };
}

function normalizeTestResult(value: unknown): PracticeTestResult | null {
  const source = asRecord(value);
  const id = normalizedString(source.id);
  const visibility = source.visibility === "hidden" ? "hidden" : "public";
  if (!id) return null;

  const result: PracticeTestResult = {
    id,
    visibility,
    passed: source.passed === true,
    verdict: normalizedVerdict(source.verdict),
  };
  const message = normalizedString(source.message);
  if (message) result.message = message;

  // Hidden test values are server-owned and must never be surfaced by a client normalizer.
  if (visibility === "public") {
    if (Object.prototype.hasOwnProperty.call(source, "input")) result.input = source.input;
    if (Object.prototype.hasOwnProperty.call(source, "expected")) result.expected = source.expected;
    if (Object.prototype.hasOwnProperty.call(source, "actual")) result.actual = source.actual;
  }
  return result;
}

function normalizeSummary(value: unknown, tests: readonly PracticeTestResult[]): PracticeSummary {
  const source = asRecord(value);
  const publicTests = tests.filter((test) => test.visibility === "public");
  const hiddenTests = tests.filter((test) => test.visibility === "hidden");
  const passedTests = tests.filter((test) => test.passed);
  return {
    public_passed: boundedInteger(source.public_passed, publicTests.filter((test) => test.passed).length, 0, 10_000),
    public_total: boundedInteger(source.public_total, publicTests.length, 0, 10_000),
    hidden_passed: boundedInteger(source.hidden_passed, hiddenTests.filter((test) => test.passed).length, 0, 10_000),
    hidden_total: boundedInteger(source.hidden_total, hiddenTests.length, 0, 10_000),
    passed: boundedInteger(source.passed, passedTests.length, 0, 10_000),
    total: boundedInteger(source.total, tests.length, 0, 10_000),
  };
}

export function normalizePracticeExecutionResponse(value: unknown): PracticeExecutionResponse {
  const source = asRecord(value);
  if (source.status !== "ok") {
    const code = normalizedString(readAlias(source, "reason", "code", "status")) || "unknown_error";
    return {
      status: "error",
      code,
      message: normalizedString(source.message) || "Practice execution failed.",
      details: Object.freeze({ ...source }),
    };
  }

  const tests = Array.isArray(source.tests)
    ? source.tests.map(normalizeTestResult).filter((test): test is PracticeTestResult => test !== null)
    : [];
  const response: PracticeExecutionSuccess = {
    status: "ok",
    mode: normalizedMode(source.mode),
    resource_id: normalizedString(source.resource_id),
    node_id: normalizedString(source.node_id),
    problem_id: normalizedString(source.problem_id),
    problem_version: normalizedString(source.problem_version),
    verdict: normalizedVerdict(source.verdict),
    tests,
    summary: normalizeSummary(source.summary, tests),
    runtime_ms: boundedNumber(source.runtime_ms),
    memory_kb: source.memory_kb === null || source.memory_kb === undefined
      ? null
      : boundedInteger(source.memory_kb, 0, 0, Number.MAX_SAFE_INTEGER),
    message: normalizedString(source.message),
  };
  const submissionId = normalizedString(source.submission_id);
  if (submissionId) response.submission_id = submissionId;
  return response;
}
