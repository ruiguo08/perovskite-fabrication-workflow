import type { EditorConfig } from "../types/api";

type JsonPath = (string | number)[];

interface SnapshotEditorProps {
  /** The planned or actual snapshot to edit (solution or process). */
  snapshot: Record<string, unknown>;
  /** Server-authoritative editor bounds from the run-sheet contract. */
  editorConfig: EditorConfig;
  /** Emits a new immutable snapshot on every edit. */
  onChange: (snapshot: Record<string, unknown>) => void;
}

const FIELD_LABELS: Record<string, string> = {
  method: "Method",
  formulation_type: "Formulation type",
  stock_dispersion: "Stock dispersion",
  stock_volume_ml: "Stock volume",
  chemical: "Chemical",
  weight_mg: "Weight",
  solvent: "Solvent",
  volume_ml: "Volume",
  rpm: "Speed",
  seconds: "Duration",
  acceleration_rpm_per_s: "Acceleration",
  temperature_c: "Temperature",
  valve: "Valve",
  pressure_pa: "Pressure",
  gas: "Gas",
  flow_sccm: "Flow",
  target_pressure_pa: "Target pressure",
  hold_seconds: "Hold time",
  sputter_mode: "Sputter mode",
  power_w: "Power",
  gas1: "Gas 1",
  gas1_flow_sccm: "Gas 1 flow",
  gas2: "Gas 2",
  gas2_flow_sccm: "Gas 2 flow",
  duration_seconds: "Duration",
  thickness_nm: "Thickness",
  rate_angstrom_per_s: "Rate",
  substrate_temperature_c: "Substrate temperature",
  cycles: "Cycles",
  solids: "Solid ingredients",
  solvents: "Solvents",
  spin_steps: "Spin-coating steps",
  anneal_steps: "Annealing steps",
  vcd_stages: "Evacuation stages",
  gas_backfill_stages: "Gas backfill stages",
  vcd_step_sequence: "VCD execution order",
};

const FIELD_UNITS: Record<string, string> = {
  stock_volume_ml: "mL",
  weight_mg: "mg",
  volume_ml: "mL",
  rpm: "rpm",
  seconds: "s",
  acceleration_rpm_per_s: "rpm/s",
  temperature_c: "°C",
  pressure_pa: "Pa",
  flow_sccm: "sccm",
  target_pressure_pa: "Pa",
  hold_seconds: "s",
  power_w: "W",
  gas1_flow_sccm: "sccm",
  gas2_flow_sccm: "sccm",
  duration_seconds: "s",
  thickness_nm: "nm",
  rate_angstrom_per_s: "Å/s",
  substrate_temperature_c: "°C",
};

const NUMERIC_FIELDS = new Set([
  "stock_volume_ml", "weight_mg", "volume_ml", "rpm", "seconds",
  "acceleration_rpm_per_s", "temperature_c", "pressure_pa", "flow_sccm",
  "target_pressure_pa", "hold_seconds", "power_w",
  "gas1_flow_sccm", "gas2_flow_sccm", "duration_seconds", "thickness_nm",
  "rate_angstrom_per_s", "substrate_temperature_c", "cycles",
]);

const INTEGER_FIELDS = new Set([
  "rpm", "seconds", "acceleration_rpm_per_s", "temperature_c",
  "pressure_pa", "target_pressure_pa", "hold_seconds", "flow_sccm",
  "duration_seconds", "cycles",
]);

interface ArrayRule {
  min: number;
  max: number;
  item: Record<string, unknown>;
}

function arrayRuleFor(key: string, config: EditorConfig): ArrayRule | null {
  switch (key) {
    case "solids":
      return { min: 1, max: config.max_solid_chemicals, item: { chemical: "", weight_mg: null } };
    case "solvents":
      return { min: 1, max: config.max_solvents, item: { solvent: "", volume_ml: null } };
    case "spin_steps":
      return { min: 1, max: 4, item: { rpm: null, seconds: null, acceleration_rpm_per_s: null } };
    case "anneal_steps":
      return { min: 1, max: 2, item: { temperature_c: null, seconds: null } };
    case "vcd_stages":
      return { min: 1, max: 5, item: { valve: "", pressure_pa: null, seconds: null } };
    case "gas_backfill_stages":
      return { min: 0, max: 5, item: { gas: "N2", flow_sccm: null, target_pressure_pa: null, hold_seconds: null } };
    default:
      return null;
  }
}

function labelFor(key: string): string {
  if (FIELD_LABELS[key]) {
    return FIELD_LABELS[key];
  }
  const spaced = key.replaceAll("_", " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function setAtPath(root: Record<string, unknown>, path: JsonPath, value: unknown): Record<string, unknown> {
  const [head, ...rest] = path;
  const clone = Array.isArray(root) ? [...root] : { ...root };
  const key = String(head);
  if (rest.length === 0) {
    (clone as Record<string, unknown>)[key] = value;
    return clone as Record<string, unknown>;
  }
  (clone as Record<string, unknown>)[key] = setAtPath(
    (clone as Record<string, unknown>)[key] as Record<string, unknown>,
    rest,
    value,
  );
  return clone as Record<string, unknown>;
}

function stagePrefix(key: string): string | null {
  if (key === "vcd_stages") return "vcd_stage";
  if (key === "gas_backfill_stages") return "gas_backfill_stage";
  return null;
}

function removeStageFromSequence(
  snapshot: Record<string, unknown>,
  key: string,
  removedIndex: number,
): Record<string, unknown> {
  const prefix = stagePrefix(key);
  const sequence = snapshot.vcd_step_sequence;
  if (!prefix || !Array.isArray(sequence)) {
    return snapshot;
  }
  const removedNumber = removedIndex + 1;
  return {
    ...snapshot,
    vcd_step_sequence: sequence
      .filter((reference) => reference !== `${prefix}${removedNumber}`)
      .map((reference) => {
        if (typeof reference !== "string" || !reference.startsWith(prefix)) {
          return reference;
        }
        const number = Number(reference.slice(prefix.length));
        return number > removedNumber ? `${prefix}${number - 1}` : reference;
      }),
  };
}

function normalizeFormulation(
  snapshot: Record<string, unknown>,
  formulationType: string,
): Record<string, unknown> {
  const next: Record<string, unknown> = { ...snapshot, formulation_type: formulationType };
  if (formulationType === "weighed_solids") {
    next.stock_dispersion = "";
    next.stock_volume_ml = null;
    const solids = Array.isArray(next.solids) ? [...next.solids] : [];
    if (solids.length === 0) {
      solids.push({ chemical: "", weight_mg: null });
    }
    next.solids = solids;
  } else {
    next.solids = [];
    next.stock_dispersion = next.stock_dispersion || "";
    next.stock_volume_ml = next.stock_volume_ml ?? null;
  }
  return next;
}

interface FieldProps {
  name: string;
  value: unknown;
  path: JsonPath;
  editorConfig: EditorConfig;
  snapshot: Record<string, unknown>;
  onChange: (snapshot: Record<string, unknown>) => void;
}

function ScalarField({ name, value, path, editorConfig, snapshot, onChange }: FieldProps) {
  const inputId = `snapshot-field-${path.join("-")}`;
  const label = `${labelFor(name)}${FIELD_UNITS[name] ? ` (${FIELD_UNITS[name]})` : ""}`;
  const update = (nextValue: unknown) => onChange(setAtPath(snapshot, path, nextValue));

  if (name === "formulation_type") {
    return (
      <label className="form-field" htmlFor={inputId}>
        <span className="form-field__label">{label}</span>
        <select
          id={inputId}
          className="text-input"
          value={String(value ?? "")}
          onChange={(event) => onChange(normalizeFormulation(snapshot, event.target.value))}
        >
          <option value="weighed_solids">Weighed solids</option>
          <option value="diluted_dispersion">Diluted dispersion</option>
        </select>
      </label>
    );
  }
  if (name === "sputter_mode") {
    return (
      <label className="form-field" htmlFor={inputId}>
        <span className="form-field__label">{label}</span>
        <select id={inputId} className="text-input" value={String(value ?? "")} onChange={(event) => update(event.target.value)}>
          {["rf", "dc", "pulsed_dc"].map((option) => (
            <option key={option} value={option}>{option.replaceAll("_", " ").toUpperCase()}</option>
          ))}
        </select>
      </label>
    );
  }
  if (name === "valve") {
    return (
      <label className="form-field" htmlFor={inputId}>
        <span className="form-field__label">{label}</span>
        <select id={inputId} className="text-input" value={String(value ?? "")} onChange={(event) => update(event.target.value)}>
          <option value="">Select valve</option>
          {editorConfig.vcd_valves.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </label>
    );
  }
  if (name === "method") {
    return (
      <label className="form-field" htmlFor={inputId}>
        <span className="form-field__label">{label}</span>
        <input id={inputId} className="text-input" readOnly value={String(value ?? "")} />
      </label>
    );
  }
  if (NUMERIC_FIELDS.has(name)) {
    return (
      <label className="form-field" htmlFor={inputId}>
        <span className="form-field__label">{label}</span>
        <input
          id={inputId}
          className="text-input"
          type="number"
          step={INTEGER_FIELDS.has(name) ? "1" : "any"}
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(event) => update(event.target.value === "" ? null : Number(event.target.value))}
        />
      </label>
    );
  }
  return (
    <label className="form-field" htmlFor={inputId}>
      <span className="form-field__label">{label}</span>
      <input id={inputId} className="text-input" value={String(value ?? "")} onChange={(event) => update(event.target.value)} />
    </label>
  );
}

interface SequenceProps {
  sequence: unknown[];
  path: JsonPath;
  snapshot: Record<string, unknown>;
  onChange: (snapshot: Record<string, unknown>) => void;
}

function SequenceEditor({ sequence, path, snapshot, onChange }: SequenceProps) {
  const swap = (index: number, direction: -1 | 1) => {
    const next = [...sequence];
    const neighbor = index + direction;
    [next[index], next[neighbor]] = [next[neighbor], next[index]];
    onChange(setAtPath(snapshot, path, next));
  };
  return (
    <section className="snapshot-sequence">
      <h4>{labelFor("vcd_step_sequence")}</h4>
      {sequence.map((referenceValue, index) => {
        const reference = String(referenceValue);
        return (
          <div className="snapshot-sequence__row" key={`${reference}-${index}`}>
            <span>
              {index + 1}. {reference.startsWith("vcd_stage") ? "Evacuate" : "Gas backfill"} (
              {reference.replace(/.*stage/, "stage ")})
            </span>
            <button
              type="button"
              className="button button--secondary button--small"
              aria-label={`Move ${reference} up`}
              disabled={index === 0}
              onClick={() => swap(index, -1)}
            >
              ↑
            </button>
            <button
              type="button"
              className="button button--secondary button--small"
              aria-label={`Move ${reference} down`}
              disabled={index === sequence.length - 1}
              onClick={() => swap(index, 1)}
            >
              ↓
            </button>
          </div>
        );
      })}
    </section>
  );
}

interface ArraySectionProps {
  name: string;
  items: unknown[];
  path: JsonPath;
  editorConfig: EditorConfig;
  snapshot: Record<string, unknown>;
  onChange: (snapshot: Record<string, unknown>) => void;
}

function ArraySection({ name, items, path, editorConfig, snapshot, onChange }: ArraySectionProps) {
  if (name === "vcd_step_sequence") {
    return <SequenceEditor sequence={items} path={path} snapshot={snapshot} onChange={onChange} />;
  }
  if (name === "solids" && snapshot.formulation_type === "diluted_dispersion") {
    return null;
  }
  const rule = arrayRuleFor(name, editorConfig);
  if (rule === null) {
    return null;
  }
  const singular = labelFor(name).replace(/s$/, "");
  const addItem = () => {
    const next = [...items, { ...rule.item }];
    const prefix = stagePrefix(name);
    if (prefix && Array.isArray(snapshot.vcd_step_sequence)) {
      const withSequence = {
        ...snapshot,
        vcd_step_sequence: [...snapshot.vcd_step_sequence, `${prefix}${next.length}`],
      };
      onChange(setAtPath(withSequence, path, next));
      return;
    }
    onChange(setAtPath(snapshot, path, next));
  };
  const removeItem = (index: number) => {
    const withoutStage = removeStageFromSequence(snapshot, name, index);
    onChange(setAtPath(withoutStage, path, items.filter((_, itemIndex) => itemIndex !== index)));
  };
  return (
    <section className="snapshot-array">
      <div className="snapshot-array__heading">
        <h4>{labelFor(name)}</h4>
        <button
          type="button"
          className="button button--secondary button--small"
          aria-label={`Add ${singular.toLowerCase()}`}
          disabled={items.length >= rule.max}
          onClick={addItem}
        >
          + Add {singular.toLowerCase()}
        </button>
      </div>
      {items.map((item, index) => (
        <div className="snapshot-array__card" key={`${name}-${index}`}>
          <div className="snapshot-array__card-header">
            <strong>{singular} {index + 1}</strong>
            <button
              type="button"
              className="button button--secondary button--small"
              aria-label={`Remove ${singular.toLowerCase()} ${index + 1}`}
              disabled={items.length <= rule.min}
              onClick={() => removeItem(index)}
            >
              Remove
            </button>
          </div>
          <ObjectFields
            object={item as Record<string, unknown>}
            path={[...path, index]}
            editorConfig={editorConfig}
            snapshot={snapshot}
            onChange={onChange}
          />
        </div>
      ))}
    </section>
  );
}

interface ObjectFieldsProps {
  object: Record<string, unknown>;
  path: JsonPath;
  editorConfig: EditorConfig;
  snapshot: Record<string, unknown>;
  onChange: (snapshot: Record<string, unknown>) => void;
}

function ObjectFields({ object, path, editorConfig, snapshot, onChange }: ObjectFieldsProps) {
  const entries = Object.entries(object);
  const scalarEntries = entries.filter(([, value]) => !Array.isArray(value));
  const arrayEntries = entries.filter(([, value]) => Array.isArray(value));
  return (
    <>
      <div className="snapshot-scalars">
        {scalarEntries.map(([key, value]) => {
          if (
            object.formulation_type === "weighed_solids" &&
            (key === "stock_dispersion" || key === "stock_volume_ml")
          ) {
            return null;
          }
          return (
            <ScalarField
              key={`${path.join("-")}-${key}`}
              name={key}
              value={value}
              path={[...path, key]}
              editorConfig={editorConfig}
              snapshot={snapshot}
              onChange={onChange}
            />
          );
        })}
      </div>
      {arrayEntries.map(([key, value]) => (
        <ArraySection
          key={`${path.join("-")}-${key}`}
          name={key}
          items={value as unknown[]}
          path={[...path, key]}
          editorConfig={editorConfig}
          snapshot={snapshot}
          onChange={onChange}
        />
      ))}
    </>
  );
}

/**
 * Editable renderer for planned and actual solution/process snapshots.
 *
 * The field metadata mirrors the legacy batch dashboard editor; all edits are
 * immutable and the component never mutates the snapshot owned by the caller.
 */
export function SnapshotEditor({ snapshot, editorConfig, onChange }: SnapshotEditorProps) {
  return (
    <div className="snapshot-editor" data-snapshot-editor="true">
      <ObjectFields
        object={snapshot}
        path={[]}
        editorConfig={editorConfig}
        snapshot={snapshot}
        onChange={onChange}
      />
    </div>
  );
}