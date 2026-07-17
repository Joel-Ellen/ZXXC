import { currentTelemetrySurface, reportClientMetric } from "./clientTelemetry";

let sentryApi = null;
let windowHandlersInstalled = false;
const instrumentedApps = new WeakSet();

const SENSITIVE_KEYS = new Set([
  "answer",
  "answers",
  "authorization",
  "code",
  "code_snippet",
  "cookie",
  "error_message",
  "password",
  "question",
  "request_body",
  "token",
]);

function configuredSampleRate(value, fallback = 0.05) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 1 ? parsed : fallback;
}

function scrubValue(value, depth = 0) {
  if (depth > 4 || value === null || value === undefined) return value;
  if (Array.isArray(value)) return value.map((item) => scrubValue(item, depth + 1));
  if (typeof value !== "object") return value;

  return Object.fromEntries(Object.entries(value).flatMap(([key, entry]) => (
    SENSITIVE_KEYS.has(key.toLowerCase())
      || /(password|token|authorization|cookie)/i.test(key)
      ? []
      : [[key, scrubValue(entry, depth + 1)]]
  )));
}

function sanitizeEvent(event) {
  const sanitized = scrubValue(event);
  if (sanitized?.request) {
    sanitized.request = {
      method: sanitized.request.method,
      url: sanitized.request.url,
    };
  }
  if (sanitized?.user) sanitized.user = undefined;
  return sanitized;
}

export async function initErrorMonitoring(app, router) {
  const dsn = String(import.meta.env.VITE_SENTRY_DSN || "").trim();
  let sentryReady = false;

  if (import.meta.env.PROD && dsn) {
    try {
      const Sentry = await import("@sentry/vue");
      Sentry.init({
        app,
        dsn,
        environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || import.meta.env.MODE,
        release: import.meta.env.VITE_SENTRY_RELEASE || undefined,
        sendDefaultPii: false,
        integrations: [Sentry.browserTracingIntegration({ router })],
        tracesSampleRate: configuredSampleRate(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE),
        beforeSend: sanitizeEvent,
      });
      sentryApi = Sentry;
      sentryReady = true;
    } catch (error) {
      console.warn("Frontend error monitoring could not be initialized.", error);
    }
  }

  installFrontendExceptionMetrics(app);
  return sentryReady;
}

function installFrontendExceptionMetrics(app) {
  if (app && !instrumentedApps.has(app)) {
    instrumentedApps.add(app);
    const previousHandler = app.config.errorHandler;
    app.config.errorHandler = (error, instance, info) => {
      void reportClientMetric("frontend_exception", {
        surface: currentTelemetrySurface(),
        kind: "vue",
      });
      if (typeof previousHandler === "function") {
        previousHandler(error, instance, info);
      } else {
        console.error(error);
      }
    };
  }

  if (windowHandlersInstalled || typeof window === "undefined") return;
  windowHandlersInstalled = true;
  window.addEventListener("error", () => {
    void reportClientMetric("frontend_exception", {
      surface: currentTelemetrySurface(),
      kind: "window",
    });
  });
  window.addEventListener("unhandledrejection", () => {
    void reportClientMetric("frontend_exception", {
      surface: currentTelemetrySurface(),
      kind: "unhandled_rejection",
    });
  });
}

export function captureApiError(error, context = {}) {
  if (!sentryApi) return;
  const status = Number(error?.response?.status);
  if (Number.isInteger(status) && status > 0 && status < 500) return;

  sentryApi.withScope((scope) => {
    if (context.requestId) scope.setTag("request_id", String(context.requestId));
    if (context.method) scope.setTag("http.method", String(context.method).toUpperCase());
    if (context.endpoint) scope.setTag("http.endpoint", String(context.endpoint));
    if (Number.isInteger(status)) scope.setTag("http.status_code", String(status));
    scope.setContext("api", scrubValue(context));
    sentryApi.captureException(error);
  });
}
