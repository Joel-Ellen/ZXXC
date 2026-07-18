import { afterEach, vi } from "vitest";

class ResizeObserverStub {
  observe() {}

  unobserve() {}

  disconnect() {}
}

Object.defineProperty(globalThis, "ResizeObserver", {
  configurable: true,
  value: ResizeObserverStub,
});

Object.defineProperty(window, "matchMedia", {
  configurable: true,
  value: vi.fn((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(() => false),
  })),
});

afterEach(() => {
  document.body.innerHTML = "";
  window.localStorage.clear();
  window.sessionStorage.clear();
});
