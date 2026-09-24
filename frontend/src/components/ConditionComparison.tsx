import { useMemo, useState } from "react";
import type {
  Condition,
  DeviceLayer,
  LayerProcess,
  LayerSolution,
  PerovskiteDepositionProcess,
} from "../types/api";

interface ComparisonRow {
  label: string;
  values: (string | null)[];
}

interface ComparisonGroup {
  key: string;
  title: string;
  meta: string | null;
  rows: ComparisonRow[];
  hasDifference: boolean;
  // Rows within the group containing at least one differing cell; rendered
  // on the summary so identical layers stay collapsed and differing layers
  // say how much changed.
  diffRowCount: number;
}

function formatSeconds(seconds: number | null): string | null {
  if (seconds === null) {
    return null;
  }
  if (seconds !== 0 && seconds % 60 === 0) {
    return `${seconds / 60} min`;
  }
  return `${seconds} s`;
}

function nullable<T>(value: T | null | undefined, render: (value: T) => string): string | null {
  return value === null || value === undefined ? null : render(value);
}

function formatSpinStep(step: { rpm: number | null; seconds: number | null; acceleration_rpm_per_s: number | null }): string | null {
  return [
    nullable(step.rpm, (value) => `${value} rpm`),
    formatSeconds(step.seconds),
    nullable(step.acceleration_rpm_per_s, (value) => `${value} rpm/s`),
  ]
    .filter(Boolean)
    .join(" · ") || null;
}

function formatAnnealStep(step: { temperature_c: number | null; seconds: number | null }): string | null {
  return [
    nullable(step.temperature_c, (value) => `${value} °C`),
    formatSeconds(step.seconds),
  ]
    .filter(Boolean)
    .join(" · ") || null;
}

function formatSolution(solution: LayerSolution | null): string | null {
  if (!solution) {
    return null;
  }
  if (solution.formulation_type === "diluted_dispersion") {
    const volume = nullable(solution.stock_volume_ml, (value) => ` · ${value} mL`);
    return `Dispersion: ${solution.stock_dispersion}${volume ?? ""}`;
  }
  const solids = solution.solids
    .filter((solid) => solid.chemical)
    .map((solid) => (solid.weight_mg !== null ? `${solid.chemical} ${solid.weight_mg} mg` : solid.chemical));
  const solvents = solution.solvents
    .filter((solvent) => solvent.solvent)
    .map((solvent) => (solvent.volume_ml !== null ? `${solvent.solvent} ${solvent.volume_ml} mL` : solvent.solvent));
  return [
    solids.length > 0 ? `Solids: ${solids.join(" · ")}` : null,
    solvents.length > 0 ? `Solvents: ${solvents.join(" · ")}` : null,
  ]
    .filter(Boolean)
    .join("\n") || null;
}

function formatLayerProcess(process: LayerProcess): string | null {
  const parts: string[] = [];
  if (process.spin_steps?.length) {
    parts.push(`Spin: ${process.spin_steps.map((step) => formatSpinStep(step) ?? "?").join(" → ")}`);
  }
  if (process.anneal_steps?.length) {
    parts.push(`Anneal: ${process.anneal_steps.map((step) => formatAnnealStep(step) ?? "?").join(" → ")}`);
  }
  const scalars: [string, string | null][] = [
    ["Mode", process.sputter_mode ?? null],
    ["Power", nullable(process.power_w, (value) => `${value} W`)],
    ["Pressure", nullable(process.pressure_pa, (value) => `${value} Pa`)],
    [
      "Gas 1",
      nullable(process.gas1, (value) =>
        process.gas1_flow_sccm != null ? `${value} ${process.gas1_flow_sccm} sccm` : value,
      ),
    ],
    [
      "Gas 2",
      nullable(process.gas2, (value) =>
        process.gas2_flow_sccm != null ? `${value} ${process.gas2_flow_sccm} sccm` : value,
      ),
    ],
    ["Duration", nullable(process.duration_seconds, (value) => formatSeconds(value) ?? `${value} s`)],
    ["Thickness", nullable(process.thickness_nm, (value) => `${value} nm`)],
    ["Rate", nullable(process.rate_angstrom_per_s, (value) => `${value} Å/s`)],
    ["Substrate temp", nullable(process.substrate_temperature_c, (value) => `${value} °C`)],
    ["ALD cycles", nullable(process.cycles, (value) => `${value}`)],
  ];
  for (const [label, value] of scalars) {
    if (value !== null) {
      parts.push(`${label}: ${value}`);
    }
  }
  return parts.length > 0 ? parts.join("\n") : process.method.replace(/_/g, " ");
}

type DepositionProcess = PerovskiteDepositionProcess | null;

function perovskiteLabels(processes: DepositionProcess[]): string[] {
  const labels: string[] = ["Method"];
  const count = (pick: (process: DepositionProcess) => unknown[] | undefined): number =>
    Math.max(0, ...processes.map((process) => pick(process)?.length ?? 0));
  const maxSpin = count((process) => process?.spin_steps);
  const maxVcd = count((process) => process?.vcd_stages);
  const maxGas = count((process) => process?.gas_backfill_stages);
  const maxAnneal = count((process) => process?.anneal_steps);
  for (let index = 0; index < maxSpin; index += 1) {
    labels.push(`Spin step ${index + 1}`);
  }
  for (let index = 0; index < maxVcd; index += 1) {
    labels.push(`VCD stage ${index + 1}`);
  }
  for (let index = 0; index < maxGas; index += 1) {
    labels.push(`Gas backfill ${index + 1}`);
  }
  labels.push("VCD sequence");
  for (let index = 0; index < maxAnneal; index += 1) {
    labels.push(`Anneal step ${index + 1}`);
  }
  return labels;
}

function perovskiteValue(process: DepositionProcess, label: string): string | null {
  if (!process) {
    return null;
  }
  if (label === "Method") {
    return process.method.replace(/_/g, " ");
  }
  if (label === "VCD sequence") {
    return process.vcd_step_sequence?.length ? process.vcd_step_sequence.join(" → ") : null;
  }
  const stepMatch = label.match(/^(Spin step|VCD stage|Gas backfill|Anneal step) (\d+)$/);
  if (!stepMatch) {
    return null;
  }
  const index = Number(stepMatch[2]) - 1;
  switch (stepMatch[1]) {
    case "Spin step": {
      const step = process.spin_steps[index];
      return step ? formatSpinStep(step) : null;
    }
    case "VCD stage": {
      const stage = process.vcd_stages[index];
      if (!stage) {
        return null;
      }
      return [
        stage.valve,
        nullable(stage.pressure_pa, (value) => `${value} Pa`),
        formatSeconds(stage.seconds),
      ]
        .filter(Boolean)
        .join(" · ") || null;
    }
    case "Gas backfill": {
      const stage = process.gas_backfill_stages[index];
      if (!stage) {
        return null;
      }
      return [
        stage.gas,
        nullable(stage.flow_sccm, (value) => `${value} sccm`),
        nullable(stage.target_pressure_pa, (value) => `${value} Pa`),
        formatSeconds(stage.hold_seconds),
      ]
        .filter(Boolean)
        .join(" · ") || null;
    }
    case "Anneal step": {
      const step = process.anneal_steps[index];
      return step ? formatAnnealStep(step) : null;
    }
    default:
      return null;
  }
}

function deviceValue(snapshot: Condition["recipe_snapshot"], label: string): string | null {
  const device = snapshot.device;
  switch (label) {
    case "Substrate": {
      const substrate = device.substrate;
      return `${substrate.material} · ${substrate.vendor} · ${substrate.type_number}`;
    }
    case "Junction":
      return device.junction_type.replace(/_/g, " ");
    case "Bandgap":
      return device.perovskite_bandgap?.replace(/_/g, " ") ?? null;
    case "Layer sequence":
      return device.layers.map((layer) => layer.name).join(" → ") || null;
    default:
      return null;
  }
}

function makeRow(label: string, values: (string | null)[]): ComparisonRow {
  return { label, values };
}

// One group per device-stack layer, in fabrication order, plus the device
// facts on top. The perovskite layer's own process (spin/VCD/anneal) is the
// condition-level deposition_process, so it is rendered as rows inside that
// layer's group: reading top to bottom reads the physical build sequence.
function buildGroups(conditions: Condition[]): { controlIndex: number; groups: ComparisonGroup[] } {
  const controlIndex = Math.max(
    0,
    conditions.findIndex((condition) => condition.role !== "target"),
  );
  const snapshots = conditions.map((condition) => condition.recipe_snapshot);
  const maxLayers = Math.max(0, ...snapshots.map((snapshot) => snapshot.device.layers.length));

  const finalize = (key: string, title: string, meta: string | null, rows: ComparisonRow[]): ComparisonGroup => {
    let diffRowCount = 0;
    for (const row of rows) {
      if (
        row.values.some(
          (value, index) => index !== controlIndex && value !== (row.values[controlIndex] ?? null),
        )
      ) {
        diffRowCount += 1;
      }
    }
    return { key, title, meta, rows, hasDifference: diffRowCount > 0, diffRowCount };
  };

  const groups: ComparisonGroup[] = [];

  groups.push(
    finalize(
      "device",
      "Device",
      null,
      ["Substrate", "Junction", "Bandgap", "Layer sequence"].map((label) =>
        makeRow(label, snapshots.map((snapshot) => deviceValue(snapshot, label))),
      ),
    ),
  );

  for (let index = 0; index < maxLayers; index += 1) {
    const controlLayer: DeviceLayer | null = snapshots[controlIndex].device.layers[index] ?? null;
    if (!conditions.some((condition) => condition.recipe_snapshot.device.layers[index])) {
      continue;
    }
    const isPerovskite = controlLayer?.layer_type === "perovskite";
    const rows: ComparisonRow[] = [
      makeRow(
        "Name",
        snapshots.map((snapshot) => {
          const layer = snapshot.device.layers[index] ?? null;
          return layer
            ? `${layer.name} (${layer.role.replace(/_/g, " ")} · ${layer.layer_type})`
            : null;
        }),
      ),
    ];
    const solutionValues = snapshots.map((snapshot) =>
      formatSolution(snapshot.device.layers[index]?.solution ?? null),
    );
    if (solutionValues.some((value) => value !== null)) {
      rows.push(makeRow("Solution", solutionValues));
    }
    if (isPerovskite) {
      const processes: DepositionProcess[] = snapshots.map(
        (snapshot) => snapshot.deposition_process ?? null,
      );
      for (const label of perovskiteLabels(processes)) {
        rows.push(makeRow(label, processes.map((process) => perovskiteValue(process, label))));
      }
    } else {
      const processValues = snapshots.map((snapshot) => {
        const layer = snapshot.device.layers[index];
        return layer?.process ? formatLayerProcess(layer.process) : null;
      });
      if (processValues.some((value) => value !== null)) {
        rows.push(makeRow("Process", processValues));
      }
    }
    groups.push(
      finalize(
        `layer-${index}`,
        `${index + 1} · ${controlLayer?.name ?? "—"}`,
        controlLayer ? controlLayer.role.replace(/_/g, " ") : null,
        rows,
      ),
    );
  }

  return { controlIndex, groups };
}

export function ConditionComparison({ conditions }: { conditions: Condition[] }) {
  const [openOverrides, setOpenOverrides] = useState<Record<string, boolean>>({});
  const { controlIndex, groups } = useMemo(() => buildGroups(conditions), [conditions]);

  return (
    <section className="condition-comparison" aria-labelledby="condition-comparison-title">
      <div className="panel__heading">
        <h3 className="panel__title" id="condition-comparison-title">Condition comparison</h3>
        <span className="condition-comparison__legend">layers in fabrication order · identical layers collapsed</span>
      </div>
      {groups.map((group) => {
        const open = openOverrides[group.key] ?? group.hasDifference;
        return (
          <details
            key={group.key}
            className="condition-comparison__group"
            open={open || undefined}
            onToggle={(event) => {
              // React nulls currentTarget once the event finishes dispatching,
              // and the state updater runs after that — read `open` now.
              const nextOpen = event.currentTarget.open;
              setOpenOverrides((current) => ({ ...current, [group.key]: nextOpen }));
            }}
          >
            <summary>
              {group.title}
              {group.meta ? <span className="condition-comparison__role">{group.meta}</span> : null}
              {group.hasDifference ? (
                <span className="condition-comparison__mark condition-comparison__mark--diff">
                  {group.diffRowCount} {group.diffRowCount === 1 ? "difference" : "differences"}
                </span>
              ) : (
                <span className="condition-comparison__mark condition-comparison__mark--same">identical</span>
              )}
            </summary>
            <div className="table-scroll">
              <table className="data-table condition-comparison__table">
                <thead>
                  <tr>
                    <th scope="col">Parameter</th>
                    {conditions.map((condition, index) => (
                      <th scope="col" key={condition.id}>
                        {condition.condition_name}
                        <span className="condition-comparison__role">
                          {condition.role}
                          {index === controlIndex ? " · reference" : ""}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {group.rows.map((row) => (
                    <tr key={row.label}>
                      <th scope="row">{row.label}</th>
                      {conditions.map((condition, index) => {
                        const value = row.values[index] ?? null;
                        const controlValue = row.values[controlIndex] ?? null;
                        const differs = index !== controlIndex && value !== controlValue;
                        return (
                          <td
                            key={condition.id}
                            className={
                              differs
                                ? "condition-comparison__cell--diff"
                                : "condition-comparison__cell--shared"
                            }
                          >
                            {value ?? "—"}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        );
      })}
    </section>
  );
}
