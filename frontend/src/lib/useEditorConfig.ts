import { useCallback } from "react";
import { apiFetch } from "./api";
import { useApiResource } from "./useApiResource";

export interface EditorConfig {
  vcd_valves: string[];
  max_solid_chemicals: number;
  max_solvents: number;
}

/**
 * Server-authoritative editor bounds (valve choices, list caps) mirroring
 * EditorConfigResponse. Callers must fall back to the local defaults while
 * the config is loading (or if it fails) — see lib/constraints.ts.
 */
export function useEditorConfig() {
  const load = useCallback(() => apiFetch<EditorConfig>("/api/editor-config"), []);
  return useApiResource(load);
}
