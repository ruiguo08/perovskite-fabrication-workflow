/**
 * Browser-local persistence for in-progress editor drafts.
 *
 * The Library pages are separate routes, so leaving an editor unmounts its
 * form and its in-memory state. Saving the draft to localStorage on every
 * change keeps the entered values across Library tab switches, page reloads,
 * and accidental navigation. Drafts are cleared on successful save or explicit
 * discard, and are keyed per user so shared lab computers do not leak one
 * student's draft into another's session.
 *
 * Shape validation is intentionally shallow: `isEmpty` keeps blank drafts out
 * of storage (and out of restore banners), and `isValid` lets the editor treat
 * a structurally unexpected object as absent.
 */

const DRAFT_STORAGE_VERSION = 1;

export interface DraftStoreOptions<T> {
  /** Storage-scope identifier, e.g. "baseline" or "experiment". */
  scope: string;
  /** Returns true when the draft carries no entered values. */
  isEmpty: (draft: T) => boolean;
  /** Minimal structural check for a value read back from storage. */
  isValid: (value: unknown) => boolean;
}

export interface DraftStore<T> {
  load(userId: number): T | null;
  save(userId: number, draft: T): void;
  clear(userId: number): void;
}

export function createDraftStore<T>(options: DraftStoreOptions<T>): DraftStore<T> {
  const storageKey = (userId: number): string =>
    `perovskite-bo:${options.scope}-draft:${userId}`;

  return {
    load(userId) {
      try {
        const raw = window.localStorage.getItem(storageKey(userId));
        if (raw === null) return null;
        const parsed = JSON.parse(raw) as { version?: unknown; draft?: unknown };
        if (
          parsed.version !== DRAFT_STORAGE_VERSION
          || !options.isValid(parsed.draft)
          || options.isEmpty(parsed.draft as T)
        ) {
          return null;
        }
        return parsed.draft as T;
      } catch {
        // Unreadable or corrupted storage is discarded rather than crashing the form.
        return null;
      }
    },
    save(userId, draft) {
      try {
        if (options.isEmpty(draft)) {
          window.localStorage.removeItem(storageKey(userId));
          return;
        }
        window.localStorage.setItem(
          storageKey(userId),
          JSON.stringify({ version: DRAFT_STORAGE_VERSION, draft }),
        );
      } catch {
        // Storage may be unavailable (quota exceeded, privacy mode); the form
        // keeps working from memory without persistence.
      }
    },
    clear(userId) {
      try {
        window.localStorage.removeItem(storageKey(userId));
      } catch {
        // Removing from unavailable storage is a no-op.
      }
    },
  };
}
