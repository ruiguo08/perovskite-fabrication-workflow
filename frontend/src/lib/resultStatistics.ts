import type { AnalysisDevice, ResultAssignmentGroup } from "../types/api";

export type MetricName = "voc" | "jsc" | "ff" | "pce";
export type ScanDirection = "forward" | "reverse";
export type StatisticsScope = "all" | "included";

export interface MetricSummary {
  maximum: number | null;
  mean: number | null;
  n: number;
}

export interface DirectionalGroupRow {
  groupId: string;
  groupName: string;
  scope: StatisticsScope;
  direction: ScanDirection;
  deviceCount: number;
  metrics: Record<MetricName, MetricSummary>;
}

const METRICS: MetricName[] = ["voc", "jsc", "ff", "pce"];
const DIRECTIONS: ScanDirection[] = ["forward", "reverse"];
const SCOPES: StatisticsScope[] = ["all", "included"];

export function directionalGroupStatistics(
  devices: AnalysisDevice[],
  groups: ResultAssignmentGroup[],
  excludedDeviceIds: Set<string>,
): DirectionalGroupRow[] {
  return groups.flatMap((group) => SCOPES.flatMap((scope) => DIRECTIONS.map((direction) => {
    const members = devices.filter((device) =>
      device.group_id === group.group_id &&
      (scope === "all" || !excludedDeviceIds.has(device.device_id)),
    );
    const metrics = Object.fromEntries(METRICS.map((metric) => {
      const values = members
        .map((device) => device.metrics?.[direction]?.[metric])
        .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
      return [metric, {
        maximum: values.length ? Math.max(...values) : null,
        mean: values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null,
        n: values.length,
      }];
    })) as Record<MetricName, MetricSummary>;
    const deviceCount = members.filter((device) => METRICS.some((metric) =>
      typeof device.metrics?.[direction]?.[metric] === "number" &&
      Number.isFinite(device.metrics?.[direction]?.[metric]),
    )).length;
    return { groupId: group.group_id, groupName: group.name, scope, direction, deviceCount, metrics };
  })));
}
