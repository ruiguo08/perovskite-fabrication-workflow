import { fieldMeta } from "../lib/fields";

function optionalNumber(value: string): number | null {
  return value === "" ? null : Number(value);
}

interface NumberFieldProps {
  /** Registry key for min/step lookup (e.g. "pressure_pa"). Optional. */
  name?: string;
  /** Full visible label, e.g. "Pressure (Pa)". */
  label: string;
  value: number | null | undefined;
  onChange: (value: number | null) => void;
  /** Override the registry step (e.g. "1" for integer stages). */
  step?: string;
}

/** Numeric input driven by the field registry (min/step) when a name is given. */
export function NumberField({ name, label, value, onChange, step }: NumberFieldProps) {
  const meta = fieldMeta(name ?? "");
  return (
    <label className="builder-field">
      <span>{label}</span>
      <input
        className="text-input"
        type="number"
        min={meta.min ?? undefined}
        step={step ?? meta.step ?? "any"}
        value={value ?? ""}
        onChange={(event) => onChange(optionalNumber(event.target.value))}
      />
    </label>
  );
}

interface SelectFieldProps {
  /** Registry key for options lookup (e.g. "valve"). */
  name?: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Override the registry options. */
  options?: readonly string[];
  /** Label for a stored value that is not among the options (e.g. a blank
   * valve). Rendered as an extra selectable option so the gap stays visible. */
  missingOptionLabel?: string;
}

/** Select input driven by the field registry (options) when a name is given. */
export function SelectField({ name, label, value, onChange, options, missingOptionLabel }: SelectFieldProps) {
  const meta = fieldMeta(name ?? "");
  const opts = options ?? meta.options ?? [];
  const rendered = opts.includes(value)
    ? opts.map((option) => ({ value: option, label: option }))
    : [{ value, label: missingOptionLabel ?? value }, ...opts.map((option) => ({ value: option, label: option }))];
  return (
    <label className="builder-field">
      <span>{label}</span>
      <select className="text-input" value={value} onChange={(event) => onChange(event.target.value)}>
        {rendered.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}
