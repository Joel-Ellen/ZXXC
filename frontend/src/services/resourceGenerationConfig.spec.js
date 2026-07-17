import { describe, expect, it } from "vitest";
import { isAsyncResourceGenerationEnabled } from "./resourceGenerationConfig";

describe("resource generation rollout flag", () => {
  it("defaults to the progressive transport for builds without the flag", () => {
    expect(isAsyncResourceGenerationEnabled({})).toBe(true);
  });

  it("accepts explicit opt-out values without disabling ordinary builds", () => {
    expect(isAsyncResourceGenerationEnabled({ VITE_RESOURCE_GENERATION_ASYNC: "false" })).toBe(false);
    expect(isAsyncResourceGenerationEnabled({ VITE_RESOURCE_GENERATION_ASYNC: "0" })).toBe(false);
    expect(isAsyncResourceGenerationEnabled({ VITE_RESOURCE_GENERATION_ASYNC: "true" })).toBe(true);
  });
});
