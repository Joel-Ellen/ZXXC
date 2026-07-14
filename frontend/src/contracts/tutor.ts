import { asRecord, normalizedString, readAlias } from "./runtime";

export const TUTOR_CONTEXT_TYPES = [
  "general",
  "concept",
  "problem_solving",
  "code_debug",
  "exam_prep",
] as const;

export type TutorContextType = typeof TUTOR_CONTEXT_TYPES[number];

export interface TutorRequest {
  question: string;
  context_type: TutorContextType;
  code_snippet: string;
  error_message: string;
  stream: boolean;
}

const CONTEXT_ALIASES: Readonly<Record<string, TutorContextType>> = Object.freeze({
  general: "general",
  study_advice: "general",
  "study-advice": "general",
  concept: "concept",
  conceptual: "concept",
  problem: "problem_solving",
  problem_solving: "problem_solving",
  "problem-solving": "problem_solving",
  code: "code_debug",
  debug: "code_debug",
  code_debug: "code_debug",
  "code-debug": "code_debug",
  exam: "exam_prep",
  exam_prep: "exam_prep",
  "exam-prep": "exam_prep",
});

export function normalizeTutorRequest(value: unknown): TutorRequest {
  const source = asRecord(value);
  const question = normalizedString(readAlias(source, "question", "query", "tutor_query"));
  if (!question) throw new TypeError("Tutor question is required");

  const rawContext = normalizedString(readAlias(source, "context_type", "contextType"))
    .toLowerCase()
    .replaceAll(" ", "_") || "general";
  const contextType = CONTEXT_ALIASES[rawContext];
  if (!contextType) throw new TypeError(`Unsupported tutor context type: ${rawContext}`);

  return {
    question,
    context_type: contextType,
    code_snippet: normalizedString(readAlias(source, "code_snippet", "codeSnippet")),
    error_message: normalizedString(readAlias(source, "error_message", "errorMessage")),
    stream: source.stream === true,
  };
}
