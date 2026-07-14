import { computed, ref } from "vue";
import { defineStore } from "pinia";
import {
  fetchSessionLearningAssets,
  patchSessionLearningAssets,
} from "../services/eduAgentApi";

const STORAGE_PREFIX = "eduagent:learning-assets:v1";

const CATEGORY_DEFAULTS = {
  tutor_history: {},
  drafts: {},
  code_drafts: {},
  quiz_progress: {},
  annotations: {},
  bookmarks: {},
  recent_learning: {},
  scroll_positions: {},
  card_state: {},
  latest_diagnostic: {},
};

const CLIENT_MUTABLE_CATEGORIES = new Set([
  "drafts",
  "code_drafts",
  "quiz_progress",
  "annotations",
  "bookmarks",
  "scroll_positions",
  "card_state",
]);

const MAX_CONFLICT_RETRIES = 2;

function clone(value) {
  if (value === undefined) return undefined;
  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return value;
  }
}

function defaultAssets() {
  return clone(CATEGORY_DEFAULTS);
}

function normalizeAssets(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const next = defaultAssets();
  for (const [category, fallback] of Object.entries(CATEGORY_DEFAULTS)) {
    const candidate = source[category];
    next[category] = candidate && typeof candidate === "object" && !Array.isArray(candidate)
      ? clone(candidate)
      : clone(fallback);
  }
  return next;
}

function storageKey(sessionId) {
  return sessionId ? `${STORAGE_PREFIX}:${sessionId}` : "";
}

function readCache(sessionId) {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(storageKey(sessionId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeCache(sessionId, value) {
  if (typeof window === "undefined" || !sessionId) return;
  try {
    window.localStorage.setItem(storageKey(sessionId), JSON.stringify(value));
  } catch {
    // Server synchronization remains the durable source when browser storage is unavailable.
  }
}

function normalizePendingPatches(value) {
  if (!Array.isArray(value)) return [];
  return value.flatMap((candidate) => {
    if (!candidate || typeof candidate !== "object") return [];
    const category = String(candidate.category || "");
    const key = String(candidate.key || "");
    if (!CLIENT_MUTABLE_CATEGORIES.has(category) || !key || key === "__all__") return [];
    if (candidate.delete === true) {
      return [{ category, key, delete: true }];
    }
    if (!("value" in candidate)) return [];
    return [{ category, key, value: clone(candidate.value) }];
  });
}

function applyPendingPatches(remoteAssets, pendingPatches) {
  const next = normalizeAssets(remoteAssets);
  for (const patch of pendingPatches) {
    const bucket = next[patch.category];
    if (!bucket || typeof bucket !== "object" || Array.isArray(bucket)) continue;
    if (patch.delete === true) {
      const updated = { ...bucket };
      delete updated[patch.key];
      next[patch.category] = updated;
    } else {
      next[patch.category] = { ...bucket, [patch.key]: clone(patch.value) };
    }
  }
  return next;
}

function errorMessage(error, fallback) {
  const reason = error?.response?.data?.reason;
  if (reason === "asset_persistence_failed") {
    return "服务端暂时无法保存，请保留本页并重试。";
  }
  return reason
    || error?.response?.data?.detail
    || error?.message
    || fallback;
}

function isRevisionConflict(error) {
  return error?.response?.status === 409
    && error?.response?.data?.reason === "asset_revision_conflict";
}

/**
 * Cross-route client state for learning assets. Local storage provides instant
 * recovery; the session assets API is the cross-device source of truth.
 */
export const useLearningAssetsStore = defineStore("learningAssets", () => {
  const sessionId = ref("");
  const assets = ref(defaultAssets());
  const revision = ref(0);
  const hydrated = ref(false);
  const syncing = ref(false);
  const syncError = ref("");
  let pendingPatches = [];
  let activePatch = null;
  let flushPromise = null;

  const hasContext = computed(() => Boolean(sessionId.value));
  const tutorHistory = computed(() => Object.entries(assets.value.tutor_history || {})
    .map(([key, entry]) => ({ ...entry, key }))
    .sort((left, right) => {
      const timestampOrder = String(left?.created_at || "").localeCompare(String(right?.created_at || ""));
      if (timestampOrder) return timestampOrder;
      if (left?.exchange_id && left.exchange_id === right?.exchange_id) {
        return Number(left?.sequence || 0) - Number(right?.sequence || 0);
      }
      return String(left?.key || "").localeCompare(String(right?.key || ""));
    }));
  const recentLearning = computed(() => Object.entries(assets.value.recent_learning || {})
    .map(([key, entry]) => ({ ...entry, key }))
    .sort((left, right) => String(
      right?.occurred_at || right?.updated_at || right?.created_at || "",
    ).localeCompare(String(left?.occurred_at || left?.updated_at || left?.created_at || ""))));

  function setSession(nextSessionId) {
    const normalized = String(nextSessionId || "");
    if (normalized === sessionId.value) return;
    const cached = readCache(normalized);
    sessionId.value = normalized;
    pendingPatches = normalizePendingPatches(cached?.pending_patches);
    assets.value = applyPendingPatches(cached?.assets, pendingPatches);
    revision.value = Number(cached?.revision) || 0;
    hydrated.value = false;
    syncing.value = false;
    syncError.value = "";
  }

  function persistLocal() {
    writeCache(sessionId.value, {
      revision: revision.value,
      assets: assets.value,
      pending_patches: pendingPatches,
      cached_at: Date.now(),
    });
  }

  function applyRemote(payload) {
    if (!payload || typeof payload !== "object") return;
    assets.value = applyPendingPatches(payload.assets ?? payload.learning_assets, pendingPatches);
    revision.value = Number(payload.revision) || revision.value;
    persistLocal();
  }

  async function hydrate(nextSessionId = sessionId.value) {
    setSession(nextSessionId);
    if (!sessionId.value) return assets.value;

    const requestSessionId = sessionId.value;
    try {
      const response = await fetchSessionLearningAssets(requestSessionId);
      if (requestSessionId !== sessionId.value) return assets.value;
      applyRemote(response);
      hydrated.value = true;
      syncError.value = "";
      void flushPending();
      return assets.value;
    } catch (error) {
      if (requestSessionId !== sessionId.value) return assets.value;
      hydrated.value = true;
      syncError.value = errorMessage(error, "Unable to synchronize learning assets.");
      persistLocal();
      return assets.value;
    }
  }

  function read(category, key, fallback = undefined) {
    const bucket = assets.value[category];
    if (key === undefined || key === null || key === "") {
      return bucket === undefined ? fallback : bucket;
    }
    if (!bucket || typeof bucket !== "object" || Array.isArray(bucket)) return fallback;
    return bucket[key] === undefined ? fallback : bucket[key];
  }

  function write(category, key, value, { sync = true } = {}) {
    if (!CLIENT_MUTABLE_CATEGORIES.has(category) || !key) return;
    const bucket = assets.value[category];
    if (!bucket || typeof bucket !== "object" || Array.isArray(bucket)) return;
    assets.value = {
      ...assets.value,
      [category]: { ...bucket, [key]: clone(value) },
    };
    persistLocal();
    if (sync) void enqueuePatch({ category, key, value: clone(value) });
  }

  function remove(category, key, { sync = true } = {}) {
    const bucket = assets.value[category];
    if (!CLIENT_MUTABLE_CATEGORIES.has(category) || !key || !bucket || typeof bucket !== "object" || Array.isArray(bucket)) {
      return;
    }
    const next = { ...bucket };
    delete next[key];
    assets.value = { ...assets.value, [category]: next };
    persistLocal();
    if (sync) void enqueuePatch({ category, key, delete: true });
  }

  function enqueuePatch(patch) {
    if (!sessionId.value) return Promise.resolve();
    const normalized = normalizePendingPatches([patch])[0];
    if (!normalized) return Promise.resolve();

    const existingIndex = pendingPatches.findIndex((candidate) => (
      candidate !== activePatch
      && candidate.category === normalized.category
      && candidate.key === normalized.key
    ));
    if (existingIndex >= 0) {
      pendingPatches.splice(existingIndex, 1, normalized);
    } else {
      pendingPatches.push(normalized);
    }
    persistLocal();
    return hydrated.value ? flushPending() : Promise.resolve();
  }

  function removePendingPatch(patch) {
    const index = pendingPatches.indexOf(patch);
    if (index >= 0) pendingPatches.splice(index, 1);
  }

  function flushPending() {
    if (!sessionId.value || !hydrated.value) return Promise.resolve();
    if (flushPromise) return flushPromise;
    const requestSessionId = sessionId.value;
    flushPromise = (async () => {
      if (requestSessionId === sessionId.value) syncing.value = true;
      while (requestSessionId === sessionId.value && pendingPatches.length) {
        const patch = pendingPatches[0];
        activePatch = patch;
        let conflictRetries = 0;
        let response = null;

        while (requestSessionId === sessionId.value) {
          try {
            response = await patchSessionLearningAssets(requestSessionId, {
              ...patch,
              base_revision: revision.value,
            });
            break;
          } catch (error) {
            const conflictPayload = error?.response?.data;
            if (isRevisionConflict(error) && conflictPayload && conflictRetries < MAX_CONFLICT_RETRIES) {
              applyRemote(conflictPayload);
              conflictRetries += 1;
              continue;
            }
            syncError.value = errorMessage(error, "Unable to save learning assets.");
            persistLocal();
            return;
          }
        }

        if (requestSessionId !== sessionId.value || !response) return;
        removePendingPatch(patch);
        activePatch = null;
        applyRemote(response);
        syncError.value = "";
      }
    })()
      .catch((error) => {
        if (requestSessionId === sessionId.value) {
          syncError.value = errorMessage(error, "Unable to save learning assets.");
          persistLocal();
        }
      })
      .finally(() => {
        activePatch = null;
        if (requestSessionId === sessionId.value) {
          syncing.value = false;
          persistLocal();
        }
        flushPromise = null;
        if (requestSessionId !== sessionId.value && hydrated.value && pendingPatches.length) {
          void flushPending();
        }
      });
    return flushPromise;
  }

  function flush() {
    persistLocal();
    return flushPending();
  }

  function reset() {
    sessionId.value = "";
    assets.value = defaultAssets();
    revision.value = 0;
    hydrated.value = false;
    syncing.value = false;
    syncError.value = "";
    pendingPatches = [];
    activePatch = null;
    flushPromise = null;
  }

  return {
    sessionId,
    assets,
    revision,
    hydrated,
    syncing,
    syncError,
    hasContext,
    tutorHistory,
    recentLearning,
    setSession,
    hydrate,
    read,
    write,
    remove,
    flush,
    flushPending,
    reset,
  };
});
