const DISABLED_VALUES = new Set(["0", "false", "off", "no"]);

/**
 * The progressive resource transport is enabled unless a deployment explicitly
 * opts out. Keeping the default on makes builds without the new environment
 * variable behave exactly like the current release.
 */
export function isAsyncResourceGenerationEnabled(env = import.meta.env) {
  const value = String(env?.VITE_RESOURCE_GENERATION_ASYNC ?? "").trim().toLowerCase();
  return !DISABLED_VALUES.has(value);
}

export const RESOURCE_GENERATION_ASYNC_ENABLED = isAsyncResourceGenerationEnabled();
