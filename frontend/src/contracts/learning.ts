import { asRecord, boundedInteger, normalizedString, readAlias } from "./runtime";
import type { UnknownRecord } from "./runtime";

export const LEARNING_EVENT_TYPES = [
  "lesson_opened",
  "content_viewed",
  "hint_requested",
  "answer_selected",
  "answer_submitted",
  "code_run",
  "code_submitted",
  "lesson_completed",
  "review_completed",
  "tutor_question",
] as const;

export type LearningEventType = typeof LEARNING_EVENT_TYPES[number];

export interface QuizAnswerEvidence {
  question_id: string;
  answer_index: number;
}

export interface QuizCompletionEvidence {
  evidence_type: string;
  resource_id: string;
  answers: QuizAnswerEvidence[];
}

export interface LearningEvent {
  event_id: string;
  event_type: LearningEventType;
  user_id: string;
  course_id: string;
  node_id: string;
  resource_id: string;
  question_id: string;
  duration_ms: number;
  attempt_number: number;
  used_hint: boolean;
  result: Readonly<UnknownRecord>;
  completion_evidence?: QuizCompletionEvidence;
}

const EVENT_TYPE_SET = new Set<string>(LEARNING_EVENT_TYPES);
const UNTRUSTED_MASTERY_FIELDS = new Set([
  "correctness",
  "mastery",
  "mastery_delta",
  "mastery_score",
  "score",
  "score_delta",
]);

function normalizedEventType(value: unknown): LearningEventType {
  const eventType = normalizedString(value).toLowerCase().replaceAll("-", "_");
  if (!EVENT_TYPE_SET.has(eventType)) {
    throw new TypeError(`Unsupported learning event type: ${eventType || "<empty>"}`);
  }
  return eventType as LearningEventType;
}

function eventInteger(
  value: unknown,
  fallback: number,
  minimum: number,
  maximum: number,
  field: string,
): number {
  if (value === undefined || value === null || value === "") return fallback;
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isInteger(numeric) || numeric < minimum || numeric > maximum) {
    throw new RangeError(`${field} must be an integer between ${minimum} and ${maximum}`);
  }
  return numeric;
}

function normalizeResult(value: unknown): Readonly<UnknownRecord> {
  const source = asRecord(value);
  return Object.freeze(Object.fromEntries(
    Object.entries(source).filter(([key]) => !UNTRUSTED_MASTERY_FIELDS.has(key)),
  ));
}

function normalizeAnswer(value: unknown): QuizAnswerEvidence | null {
  const source = asRecord(value);
  const questionId = normalizedString(readAlias(source, "question_id", "questionId", "id"));
  const answerIndex = boundedInteger(
    readAlias(
      source,
      "answer_index",
      "answerIndex",
      "selected_option_index",
      "selectedOptionIndex",
    ),
    -1,
    -1,
    10_000,
  );
  return questionId && answerIndex >= 0 ? { question_id: questionId, answer_index: answerIndex } : null;
}

function normalizeCompletionEvidence(value: unknown): QuizCompletionEvidence | undefined {
  const source = asRecord(value);
  if (!Object.keys(source).length) return undefined;
  const rawAnswers = source.answers;
  const answers = Array.isArray(rawAnswers)
    ? rawAnswers.map(normalizeAnswer).filter((answer): answer is QuizAnswerEvidence => answer !== null)
    : [];
  return {
    evidence_type: normalizedString(readAlias(source, "evidence_type", "evidenceType", "type"))
      || "diagnostic_quiz",
    resource_id: normalizedString(readAlias(source, "resource_id", "resourceId")),
    answers,
  };
}

export function normalizeLearningEvent(value: unknown): LearningEvent {
  const source = asRecord(value);
  const completionEvidence = normalizeCompletionEvidence(
    readAlias(source, "completion_evidence", "completionEvidence", "evidence"),
  );
  const event: LearningEvent = {
    event_id: normalizedString(readAlias(source, "event_id", "eventId", "id")),
    event_type: normalizedEventType(readAlias(source, "event_type", "eventType")),
    user_id: normalizedString(readAlias(source, "user_id", "userId")),
    course_id: normalizedString(readAlias(source, "course_id", "courseId")),
    node_id: normalizedString(readAlias(source, "node_id", "nodeId")),
    resource_id: normalizedString(readAlias(source, "resource_id", "resourceId")),
    question_id: normalizedString(readAlias(source, "question_id", "questionId")),
    duration_ms: eventInteger(
      readAlias(source, "duration_ms", "durationMs"),
      0,
      0,
      86_400_000,
      "duration_ms",
    ),
    attempt_number: eventInteger(
      readAlias(source, "attempt_number", "attemptNumber"),
      1,
      1,
      10_000,
      "attempt_number",
    ),
    used_hint: readAlias(source, "used_hint", "usedHint") === true,
    result: normalizeResult(source.result),
  };
  if (completionEvidence) event.completion_evidence = completionEvidence;
  return event;
}
