import { describe, expect, it } from "vitest";
import {
  CODE_LANGUAGE,
  CODE_LANGUAGE_LABEL,
  DEFAULT_C_STARTER_CODE,
  extractCCode,
  normalizeCodeLanguage,
  resolveStructuredPayload,
} from "./codeExample.js";

describe("code example contract", () => {
  it("normalizes every learner-facing example to C", () => {
    expect(normalizeCodeLanguage()).toBe(CODE_LANGUAGE);
    expect(normalizeCodeLanguage("python")).toBe(CODE_LANGUAGE);
    expect(CODE_LANGUAGE_LABEL).toBe("C");
  });

  it("unwraps both current and legacy resource payloads", () => {
    const payload = { language: "c", code: "int main(void) { return 0; }" };
    expect(resolveStructuredPayload({ structured_payload: payload })).toEqual(payload);
    expect(resolveStructuredPayload({ metadata: { structured_payload: payload } })).toEqual(payload);
    expect(resolveStructuredPayload({ structured_payload: {}, metadata: { structured_payload: payload } }))
      .toEqual(payload);
  });

  it("keeps the neutral C scaffold compatible with the server test harness", () => {
    expect(DEFAULT_C_STARTER_CODE).toContain("#include <stddef.h>");
    expect(DEFAULT_C_STARTER_CODE).not.toMatch(/\bmain\s*\(/);
  });

  it("never exposes a stale Python payload as a C example", () => {
    expect(extractCCode({
      structured_payload: {
        language: "python",
        code: "def answer():\n    return 42",
      },
      content: "```python\ndef answer():\n    return 42\n```",
    })).toBe("");
    expect(extractCCode({
      content: "```python\ndef answer():\n    return 42\n```",
    })).toBe("");
  });

  it("extracts C from canonical and fenced payloads", () => {
    const source = "int answer(void) { return 42; }";
    expect(extractCCode({ structured_payload: { language: "c", code: source } })).toBe(source);
    expect(extractCCode({ content: `说明\n\`\`\`c\n${source}\n\`\`\`` })).toBe(source);
  });

  it("skips an earlier non-C fence when a later C example is available", () => {
    const source = "int answer(void) { return 42; }";
    expect(extractCCode({
      content: `输入格式\n\`\`\`\n1 2 3\n\`\`\`\n示例代码\n\`\`\`c11\n${source}\n\`\`\``,
    })).toBe(source);
  });
});
