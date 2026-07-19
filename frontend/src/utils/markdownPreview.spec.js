import { describe, expect, it } from "vitest";
import { extractCode, extractCodePreview } from "./markdownPreview.js";

describe("markdown code extraction", () => {
  it("keeps the complete fenced source for detail views", () => {
    const source = Array.from({ length: 64 }, (_, index) => `int value_${index}(void) { return ${index}; }`).join("\n");

    expect(extractCode(`## 示例\n\n\`\`\`c\n${source}\n\`\`\``)).toBe(source);
    expect(extractCodePreview(`\`\`\`c\n${source}\n\`\`\``, 8).split("\n")).toHaveLength(8);
  });
});
