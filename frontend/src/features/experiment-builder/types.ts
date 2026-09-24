import type {
  DeviceLayer,
  DeviceRecipe,
  DeviceSubstrate,
  PerovskiteDepositionProcess,
} from "../../types/api";

export type BuilderPlanType = "comparative" | "standalone";

export interface BuilderCondition {
  group_id: string;
  kind: "control" | "target" | "standalone";
  name: string;
  layers: DeviceLayer[];
  deposition_process: PerovskiteDepositionProcess;
  device_layout_code: string;
  planned_substrate_count: number;
}

export interface ExperimentDraft {
  campaign_id: string;
  source_baseline_version_id: number | null;
  source_baseline_name: string | null;
  setup_mode: "baseline" | "blank";
  junction_type: string;
  perovskite_bandgap: string;
  architecture: "pin" | "nip";
  substrate: DeviceSubstrate;
  layers: DeviceLayer[];
  deposition_process: PerovskiteDepositionProcess;
  plan_type: BuilderPlanType;
  conditions: BuilderCondition[];
}

export interface ExperimentCreatePayload {
  campaign_id: string;
  source_baseline_version_id: number | null;
  recipe: Record<string, unknown> & { device_recipe: DeviceRecipe };
  condition_plans: Array<{
    group_id: string;
    role: "control" | "target" | "standalone";
    device_layout_code: string;
    planned_substrate_count: number;
  }>;
}

export interface DraftIssue {
  path: string;
  message: string;
}
