import { useCallback, useEffect, useRef, useState } from "react";

export type ResourceStatus = "loading" | "success" | "error";

/** Outcome of a reload call: whether this call's response was applied. */
export type ReloadOutcome = "applied" | "superseded" | "failed";

export interface ApiResource<T> {
  status: ResourceStatus;
  data: T | null;
  error: string | null;
  /**
   * Reload the loader; never rejects. Resolves "applied" when this call's
   * response became the resource data, "superseded" when a newer request
   * took over before the response landed, and "failed" on a fetch error.
   */
  reload: () => Promise<ReloadOutcome>;
}

export interface UseApiResourceOptions {
  /** Clear existing data when the loader identity changes (stale filter safety). */
  resetOnLoaderChange?: boolean;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}

/**
 * Load one API resource while suppressing stale or unmounted responses.
 *
 * `reload` never rejects: it reports whether this call's response was
 * applied so callers never toast or clear optimistic state for data that a
 * newer in-flight request already superseded.
 */
export function useApiResource<T>(
  loader: () => Promise<T>,
  options?: UseApiResourceOptions,
): ApiResource<T> {
  const resetOnLoaderChange = options?.resetOnLoaderChange ?? false;
  const [status, setStatus] = useState<ResourceStatus>("loading");
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);
  const mounted = useRef(true);
  const previousLoader = useRef(loader);

  const reload = useCallback(async (): Promise<ReloadOutcome> => {
    const activeRequest = ++requestId.current;
    setStatus("loading");
    setError(null);
    try {
      const value = await loader();
      if (mounted.current && requestId.current === activeRequest) {
        setData(value);
        setStatus("success");
        return "applied";
      }
      return "superseded";
    } catch (loadError) {
      if (mounted.current && requestId.current === activeRequest) {
        setError(errorMessage(loadError));
        setStatus("error");
      }
      return "failed";
    }
  }, [loader]);

  useEffect(() => {
    if (resetOnLoaderChange && previousLoader.current !== loader) {
      setData(null);
    }
    previousLoader.current = loader;
    mounted.current = true;
    void reload();
    return () => {
      mounted.current = false;
      requestId.current += 1;
    };
  }, [reload, resetOnLoaderChange, loader]);

  return { status, data, error, reload };
}