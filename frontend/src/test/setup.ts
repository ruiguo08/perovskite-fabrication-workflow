import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length() {
    return this.values.size;
  }

  clear() {
    this.values.clear();
  }

  getItem(key: string) {
    return this.values.get(String(key)) ?? null;
  }

  key(index: number) {
    return Array.from(this.values.keys())[index] ?? null;
  }

  removeItem(key: string) {
    this.values.delete(String(key));
  }

  setItem(key: string, value: string) {
    this.values.set(String(key), String(value));
  }
}

// Node 26 exposes a global localStorage accessor that returns undefined unless
// the process receives --localstorage-file. Vitest workers copy that accessor
// into jsdom and shadow jsdom's Storage implementation. Define a deterministic
// browser-compatible store in the shared test environment instead of coupling
// the test command to a process-global file.
Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: new MemoryStorage(),
});

// With `globals: false` the testing-library auto-cleanup hook is not
// registered; run it explicitly so tests do not share the document.
afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
