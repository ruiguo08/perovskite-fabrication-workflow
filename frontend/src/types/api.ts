export type Role = "student" | "instructor" | "administrator";

export interface DeviceSubstrate {
  material: string;
  vendor: string;
  type_number: string;
  width_mm: number;
  length_mm: number;
}

export interface SolutionSolid {
  chemical: string;
  weight_mg: number | null;
}

export interface SolutionSolvent {
  solvent: string;
  volume_ml: number | null;
}

export interface LayerSolution {
  formulation_type: "weighed_solids" | "diluted_dispersion";
  stock_dispersion: string;
  stock_volume_ml: number | null;
  solids: SolutionSolid[];
  solvents: SolutionSolvent[];
}

export interface SpinStep {
  rpm: number | null;
  seconds: number | null;
  acceleration_rpm_per_s: number | null;
}

export interface AnnealStep {
  temperature_c: number | null;
  seconds: number | null;
}

export interface VcdStage {
  valve: string;
  pressure_pa: number | null;
  seconds: number | null;
}

export interface GasBackfillStage {
  gas: string;
  flow_sccm: number | null;
  target_pressure_pa: number | null;
  hold_seconds: number | null;
}

export interface LayerProcess {
  method: string;
  spin_steps?: SpinStep[];
  anneal_steps?: AnnealStep[];
  sputter_mode?: string;
  power_w?: number | null;
  pressure_pa?: number | null;
  gas1?: string;
  gas1_flow_sccm?: number | null;
  gas2?: string;
  gas2_flow_sccm?: number | null;
  duration_seconds?: number | null;
  thickness_nm?: number | null;
  rate_angstrom_per_s?: number | null;
  substrate_temperature_c?: number | null;
  cycles?: number | null;
}

export interface PerovskiteDepositionProcess {
  method: "spin_coating_vcd";
  spin_steps: SpinStep[];
  vcd_stages: VcdStage[];
  gas_backfill_stages: GasBackfillStage[];
  vcd_step_sequence?: string[] | null;
  anneal_steps: AnnealStep[];
}

export interface DeviceLayer {
  layer_type: string;
  role: string;
  name: string;
  preset_id: string | null;
  solution: LayerSolution | null;
  process: LayerProcess | null;
}

export interface ExperimentGroup {
  group_id: string;
  kind: "control" | "target" | "standalone";
  name: string;
  change_from_control: string;
  inherits_control: boolean;
  adjustments: Record<string, unknown>[];
  layers?: DeviceLayer[] | null;
  deposition_process?: PerovskiteDepositionProcess | null;
  substrate_count?: number | null;
}

export interface DeviceRecipe {
  schema_version: number;
  junction_type: string;
  perovskite_bandgap: string;
  architecture: "pin" | "nip";
  setup_mode: string;
  experimental_groups: ExperimentGroup[];
  substrate: DeviceSubstrate;
  layers: DeviceLayer[];
}

export interface DepositionRecipe {
  device_recipe: DeviceRecipe | null;
  [field: string]: unknown;
}

export interface ConditionDeviceConfiguration {
  schema_version: number;
  setup_mode: string;
  junction_type: string;
  perovskite_bandgap: string | null;
  tandem_type?: string | null;
  substrate: DeviceSubstrate;
  layers: DeviceLayer[];
}

export interface ConditionRecipeSnapshot {
  schema_version: number;
  device: ConditionDeviceConfiguration;
  deposition_process: PerovskiteDepositionProcess;
}

export interface Experiment {
  id: number;
  recipe: DepositionRecipe;
  status: string;
  metrics: Record<string, number>;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
  campaign_id: string | null;
  experiment_code: string | null;
  series_version: number | null;
  plan_type: string | null;
  plan_status: string | null;
  device_summary: string | null;
}

export interface Condition {
  id: number;
  experiment_id: number;
  role: string;
  condition_code: string;
  condition_name: string;
  recipe_snapshot: ConditionRecipeSnapshot;
  recipe_schema_version: number;
  canonical_hash: string;
  source_baseline_version_id: number | null;
  device_layout_code: string;
  device_layout_snapshot: Record<string, unknown>;
  planned_substrate_count: number;
  expected_device_count: number;
  requires_manual_review: boolean;
  created_at: string;
}

export interface SubstrateException {
  id: number;
  condition_id: number;
  requested_count: number;
  reason: string;
  requested_by_id: number | null;
  requested_at: string;
  decision: string;
  decided_by_id: number | null;
  decided_at: string | null;
  decision_note: string;
  approved_condition_hash: string | null;
}

export interface FabricationBatchSummary {
  id: number;
  experiment_id: number;
  batch_number: number;
  batch_code: string;
  status: string;
  condition_set_hash: string;
  notes: string;
  created_by_id: number | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
}

export interface ResultSummary {
  id: number;
  experiment_id: number;
  fabrication_batch_id: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  group_assignment: string;
  metrics: Record<string, number>;
  analysis_schema_version: number;
  created_at: string;
}

export interface ExperimentDetail {
  experiment: Experiment;
  conditions: Condition[];
  substrate_exceptions: SubstrateException[];
  fabrication_batches: FabricationBatchSummary[];
  results: ResultSummary[];
}

export interface Baseline {
  id: number;
  name: string;
  status: string;
  scope: "personal" | "shared";
  owner_user_id: number | null;
  owner_display_name: string | null;
  promoted_by_user_id: number | null;
  promoted_by_display_name: string | null;
  promoted_at: string | null;
  promotion_note: string | null;
  promoted_version_id: number | null;
  device_recipe: DeviceRecipe;
  deposition_process: PerovskiteDepositionProcess | null;
  current_revision_number: number | null;
  current_version_id: number | null;
  canonical_hash: string | null;
  created_at: string;
  updated_at: string;
}

export interface BaselineVersion {
  id: number;
  baseline_id: number;
  revision_number: number;
  recipe_schema_version: number;
  device_recipe: DeviceRecipe;
  deposition_process: PerovskiteDepositionProcess;
  canonical_hash: string;
  change_note: string;
  created_by_id: number | null;
  created_at: string;
}

export interface LayerPreset {
  id: number;
  preset_key: string;
  name: string;
  status: string;
  scope: "personal" | "shared";
  layer: DeviceLayer;
  deposition_process: PerovskiteDepositionProcess | null;
  current_revision_number: number;
  current_version_id: number;
  canonical_hash: string;
  created_at: string;
  updated_at: string;
}

export interface LayerPresetVersion {
  id: number;
  layer_preset_id: number;
  revision_number: number;
  preset_schema_version: number;
  layer: DeviceLayer;
  deposition_process: PerovskiteDepositionProcess | null;
  canonical_hash: string;
  created_by_id: number | null;
  created_at: string;
}

export interface MaterialProduct {
  id: number;
  vendor: string;
  catalog_number: string;
  specification: Record<string, unknown>;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Material {
  id: number;
  category: string;
  name: string;
  formula: string;
  cas_number: string;
  specification: Record<string, unknown>;
  status: string;
  products: MaterialProduct[];
  created_at: string;
  updated_at: string;
}

export interface Campaign {
  id: number;
  code: string;
  display_name: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface DeviceLayout {
  code: string;
  version: number;
  substrate_width_mm: string;
  substrate_length_mm: string;
  devices_per_substrate: number;
  device_active_area_cm2: string;
  total_active_area_cm2: string;
  description: string;
}

export interface UserAccount {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  locked_until: string | null;
  last_login_at: string | null;
  password_changed_at: string;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Phase 3 — fabrication batches, results, and provenance contracts
// ---------------------------------------------------------------------------

export interface FabricationBatchListItem {
  id: number;
  experiment_id: number;
  experiment_code: string | null;
  batch_number: number;
  batch_code: string;
  status: string;
  condition_set_hash: string;
  notes: string;
  created_by_id: number | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
}

export interface ResultListItem {
  id: number;
  experiment_id: number;
  experiment_code: string | null;
  fabrication_batch_id: number;
  batch_code: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  group_assignment: string;
  metrics: Record<string, number>;
  analysis_schema_version: number;
  created_at: string;
}

/**
 * Completion-only shortfall explanation: just the condition and the reason.
 * The server derives category, severity, and planned/actual values from
 * authoritative batch data inside the completion transaction.
 */
export interface CompletionShortfallDeviation {
  condition_id: number;
  description: string;
}

export interface FrozenBatchCondition {
  id: number;
  fabrication_batch_id: number;
  source_condition_id: number;
  condition_code: string;
  condition_name: string;
  role: string;
  source_condition_hash: string;
  recipe_snapshot: Record<string, unknown>;
  recipe_schema_version: number;
  device_layout_code: string;
  device_layout_snapshot: Record<string, unknown>;
  planned_substrate_count: number;
  expected_device_count: number;
  actual_substrate_count: number | null;
}

export interface FabricationSubstrate {
  id: number;
  batch_condition_id: number;
  substrate_ordinal: number;
  substrate_code: string;
  substrate_mark: string;
  status: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface FabricationDevice {
  id: number;
  substrate_id: number;
  device_ordinal: number;
  device_code: string;
  device_mark: string;
  device_active_area_cm2: string;
  status: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface SolutionPreparationUse {
  id: number;
  solution_preparation_id: number;
  batch_condition_id: number;
  layer_ordinal: number;
  layer_role: string;
  layer_type: string;
  layer_snapshot_hash: string;
}

export interface SolutionPreparation {
  id: number;
  fabrication_batch_id: number;
  preparation_code: string;
  status: string;
  planned_solution_snapshot: Record<string, unknown>;
  planned_snapshot_schema_version: number;
  planned_canonical_hash: string;
  actual_solution_snapshot: Record<string, unknown> | null;
  actual_snapshot_schema_version: number | null;
  actual_canonical_hash: string | null;
  actual_recording_mode: string | null;
  prepared_by_id: number | null;
  prepared_at: string | null;
  completed_at: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface ProcessExecutionMember {
  id: number;
  process_execution_id: number;
  substrate_id: number;
  batch_condition_id: number;
  layer_ordinal: number;
  layer_snapshot_hash: string;
}

export interface ProcessExecution {
  id: number;
  fabrication_batch_id: number;
  execution_code: string;
  method: string;
  layer_role: string;
  layer_type: string;
  layer_name: string;
  status: string;
  is_shared: boolean;
  planned_process_snapshot: Record<string, unknown>;
  planned_snapshot_schema_version: number;
  planned_canonical_hash: string;
  actual_process_snapshot: Record<string, unknown> | null;
  actual_snapshot_schema_version: number | null;
  actual_canonical_hash: string | null;
  actual_recording_mode: string | null;
  equipment_identifier: string | null;
  executed_by_id: number | null;
  started_at: string | null;
  completed_at: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface Deviation {
  id: number;
  fabrication_batch_id: number;
  category: string;
  severity: string;
  /** Semantic type: general | fabrication_shortfall | measurement_shortfall */
  deviation_type: string;
  description: string;
  planned_value: Record<string, unknown> | null;
  actual_value: Record<string, unknown> | null;
  recorded_by_id: number | null;
  recorded_at: string;
  supersedes_deviation_id: number | null;
  solution_preparation_id: number | null;
  process_execution_id: number | null;
  substrate_id: number | null;
  device_id: number | null;
  created_at: string;
}

export interface EditorConfig {
  vcd_valves: string[];
  max_solid_chemicals: number;
  max_solvents: number;
}

export interface RunSheetPreparation {
  preparation: SolutionPreparation;
  uses: SolutionPreparationUse[];
}

export interface RunSheetExecution {
  execution: ProcessExecution;
  members: ProcessExecutionMember[];
}

export interface BatchRunSheet {
  batch: FabricationBatchSummary;
  conditions: FrozenBatchCondition[];
  substrates: FabricationSubstrate[];
  devices: FabricationDevice[];
  preparations: RunSheetPreparation[];
  executions: RunSheetExecution[];
  deviations: Deviation[];
  editor_config: EditorConfig;
}

export interface ResultAssignmentGroup {
  group_id: string;
  batch_condition_id: number;
  condition_code: string;
  kind: string;
  name: string;
}

export interface ResultAssignment {
  id: number;
  result_file_id: number;
  analysis_device_id: string;
  analysis_substrate_id: string;
  instrument_label: string;
  fabrication_device_id: number | null;
  device_code: string | null;
  device_mark: string | null;
  substrate_id: number | null;
  substrate_code: string | null;
  substrate_mark: string | null;
  batch_condition_id: number;
  source_condition_id: number;
  condition_code: string;
  condition_name: string;
  created_at: string;
}

export interface ResultDetail {
  id: number;
  experiment_id: number;
  fabrication_batch_id: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  group_assignment: string;
  metrics: Record<string, number>;
  analysis: Record<string, unknown>;
  analysis_schema_version: number;
  created_by_id: number | null;
  created_at: string;
  groups: ResultAssignmentGroup[];
  assignments: ResultAssignment[];
}

export interface ResultAssignmentItem {
  analysis_substrate_id: string;
  batch_condition_id: number;
}

export interface AssignmentsPayload {
  assignments: ResultAssignmentItem[];
}

// ---------------------------------------------------------------------------
// Phase 3C — parsed JV analysis contracts (server-computed; never mutated client-side)
// ---------------------------------------------------------------------------

export interface AnalysisTrace {
  trace_id: string;
  label: string;
  direction: string;
  measured_at: string | null;
  valid: boolean;
  error: string | null;
  metrics: Record<string, number> | null;
  points: number[][];
  /** Verbatim label/value info rows of the instrument trace block (schema 4+). */
  info?: Record<string, string>;
  /** Where the metrics came from: "summary table", "[Statistic] section",
   * "info rows", or "recomputed from curve" (schema 6+). */
  metric_source?: string | null;
}

/** Per-scan-direction metrics (schema 6). Forward and reverse sweeps probe
 * different physics — their divergence (hysteresis) is the signal — so the
 * values are stored per direction and never merged. `combined` only appears
 * on analyses migrated from schema 5, whose flat values cannot be split. */
export type DirectionalMetrics = {
  forward: Record<string, number> | null;
  reverse: Record<string, number> | null;
  combined?: Record<string, number> | null;
};

export interface AnalysisDevice {
  device_id: string;
  label: string;
  device_mark: string | null;
  substrate_id: string;
  group_id: string;
  metrics: DirectionalMetrics | null;
  traces: AnalysisTrace[];
  /** Flagged outlier: kept for provenance but skipped by statistics. */
  excluded?: boolean;
  exclusion_reason?: string | null;
  /** Relative forward/reverse PCE divergence; null when a direction is missing (schema 5+). */
  hysteresis_index?: number | null;
  /** Illumination reported by the instrument in suns (schema 5+). */
  irradiance_sun?: number | null;
}

// ---------------------------------------------------------------------------
// Device scan history (schema 7): every scan of a physical device across all
// uploads, with the per-direction representative the UI shows by default.
// ---------------------------------------------------------------------------

export interface DeviceScanRecord {
  result_file_id: number;
  filename: string;
  uploaded_at: string;
  trace_id: string;
  direction: string;
  valid: boolean;
  measured_at: string | null;
  metrics: Record<string, number> | null;
  metric_source: string | null;
  error: string | null;
  points: number[][];
}

export interface RepresentativeScan {
  result_file_id: number;
  trace_id: string;
  measured_at: string | null;
  metrics: Record<string, number>;
  metric_source: string | null;
  /** True when the user pinned this scan explicitly (vs the best-PCE default). */
  from_user_selection: boolean;
}

export interface DeviceJvScans {
  fabrication_device_id: number;
  device_code: string;
  device_mark: string | null;
  device_ordinal: number;
  substrate_id: number;
  substrate_code: string;
  scans: DeviceScanRecord[];
  representative: { forward: RepresentativeScan | null; reverse: RepresentativeScan | null };
  scan_counts: { forward: number; reverse: number };
}

export interface AnalysisSubstrate {
  substrate_id: string;
  device_ids: string[];
  instrument_labels: string[];
  group_id: string;
  batch_condition_id?: number;
}

export interface AnalysisGroupMetric {
  n: number;
  mean: number | null;
  median: number | null;
  sd: number | null;
  minimum: number | null;
  q1: number | null;
  q3: number | null;
  maximum: number | null;
}

export interface AnalysisGroupStat {
  group_id: string;
  name: string;
  kind: string;
  device_count: number;
  valid_device_count: number;
  /** Devices flagged as excluded outliers within this group (schema 4+). */
  excluded_device_count?: number;
    metrics: Record<"forward" | "reverse", Record<string, AnalysisGroupMetric>>;
}

export interface AnalysisComparisonMetric {
  mean_difference: number | null;
  percent_difference: number | null;
  effect_size: number | null;
  p_value: number | null;
  adjusted_p_value: number | null;
  test_method: string | null;
}

export interface AnalysisComparison {
  target_group_id: string;
  target_name: string;
    control_name: string;
    direction: "forward" | "reverse";
  metrics: Record<string, AnalysisComparisonMetric | null>;
}

export interface AnalysisStatistics {
  groups: AnalysisGroupStat[];
  comparisons: AnalysisComparison[];
}

export interface UnitConversion {
  source_column: string;
  source_unit: string;
  device_active_area_cm2: number;
  converted_to: string;
}

export interface ParsedAnalysis {
  schema_version: number;
  devices: AnalysisDevice[];
  substrates: AnalysisSubstrate[];
  /** Parse-time snapshot over every device; never changes with exclusions. */
  acquisition_summary?: Record<string, number>;
  /** Exclusion-aware analytic summary, recomputed when devices are excluded. */
  summary: Record<string, number>;
  statistics: AnalysisStatistics | Record<string, never>;
  /** Upload-level advisory messages, e.g. non-1-sun illumination (schema 5+). */
  warnings?: string[];
  /** Recorded when a total-current column was converted with J = I / A (schema 5+). */
  unit_conversion?: UnitConversion | null;
}
