import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useApiResource } from "./useApiResource";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("useApiResource", () => {
  it("moves from loading to success", async () => {
    const load = vi.fn().mockResolvedValue(["alpha"]);

    const { result } = renderHook(() => useApiResource(load));

    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.data).toEqual(["alpha"]);
    expect(result.current.error).toBeNull();
  });

  it("exposes errors and retries without dropping existing data", async () => {
    const load = vi
      .fn<() => Promise<string[]>>()
      .mockResolvedValueOnce(["first"])
      .mockRejectedValueOnce(new Error("Directory unavailable"));
    const { result } = renderHook(() => useApiResource(load));
    await waitFor(() => expect(result.current.status).toBe("success"));

    await act(async () => {
      await result.current.reload();
    });

    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe("Directory unavailable");
    expect(result.current.data).toEqual(["first"]);
  });

  it("does not let an older response replace a newer reload", async () => {
    const older = deferred<string[]>();
    const newer = deferred<string[]>();
    const load = vi
      .fn<() => Promise<string[]>>()
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);
    const { result } = renderHook(() => useApiResource(load));

    act(() => {
      void result.current.reload();
    });
    await act(async () => {
      newer.resolve(["new"]);
      await newer.promise;
    });
    await waitFor(() => expect(result.current.data).toEqual(["new"]));

    await act(async () => {
      older.resolve(["old"]);
      await older.promise;
    });

    expect(result.current.data).toEqual(["new"]);
  });

  it("resolves reload with an outcome string instead of rejecting", async () => {
    const load = vi
      .fn<() => Promise<string[]>>()
      .mockResolvedValueOnce(["first"])
      .mockRejectedValueOnce(new Error("Directory unavailable"));
    const { result } = renderHook(() => useApiResource(load));
    await waitFor(() => expect(result.current.status).toBe("success"));

    let outcome: string | undefined;
    await act(async () => {
      outcome = await result.current.reload();
    });
    expect(outcome).toBe("failed");
    expect(result.current.status).toBe("error");
    expect(result.current.data).toEqual(["first"]);

    await act(async () => {
      outcome = await result.current.reload();
    });
    expect(outcome).toBe("applied");
    expect(result.current.status).toBe("success");
  });

  it("resolves 'superseded' when a newer reload started before the response landed", async () => {
    const older = deferred<string[]>();
    const newer = deferred<string[]>();
    const load = vi
      .fn<() => Promise<string[]>>()
      .mockResolvedValueOnce(["mount"])
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);
    const { result } = renderHook(() => useApiResource(load));
    await waitFor(() => expect(result.current.data).toEqual(["mount"]));

    let olderOutcome: string | undefined;
    let newerOutcome: string | undefined;
    act(() => {
      void result.current.reload().then((outcome) => {
        olderOutcome = outcome;
      });
    });
    act(() => {
      void result.current.reload().then((outcome) => {
        newerOutcome = outcome;
      });
    });
    await act(async () => {
      newer.resolve(["new"]);
      await newer.promise;
    });
    await act(async () => {
      older.resolve(["old"]);
      await older.promise;
    });

    expect(olderOutcome).toBe("superseded");
    expect(newerOutcome).toBe("applied");
    expect(result.current.data).toEqual(["new"]);
  });

  it("clears stale data when the loader identity changes with resetOnLoaderChange", async () => {
    const firstLoad = vi.fn<() => Promise<string[]>>().mockResolvedValue(["draft"]);
    const secondLoad = vi.fn<() => Promise<string[]>>().mockResolvedValue(["completed"]);
    const { result, rerender } = renderHook(
      ({ loader }: { loader: () => Promise<string[]> }) => useApiResource(loader, { resetOnLoaderChange: true }),
      { initialProps: { loader: firstLoad } },
    );
    await waitFor(() => expect(result.current.data).toEqual(["draft"]));

    rerender({ loader: secondLoad });
    expect(result.current.status).toBe("loading");
    expect(result.current.data).toBeNull();

    await waitFor(() => expect(result.current.data).toEqual(["completed"]));
  });
});
