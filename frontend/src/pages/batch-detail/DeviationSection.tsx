import { useMemo, useState, type FormEvent } from "react";
import { InlineFormError } from "../../components/InlineFormError";
import type { BatchRunSheet } from "../../types/api";
import { parseJsonField } from "./helpers";

interface DeviationSectionProps {
  sheet: BatchRunSheet;
  onSubmit: (payload: Record<string, unknown>) => Promise<void>;
  disabled: boolean;
}

export function DeviationSection({ sheet, onSubmit, disabled }: DeviationSectionProps) {
  const [category, setCategory] = useState("process");
  const [severity, setSeverity] = useState("warning");
  const [deviationType, setDeviationType] = useState("general");
  const [target, setTarget] = useState("");
  const [description, setDescription] = useState("");
  const [planned, setPlanned] = useState("");
  const [actual, setActual] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const targets = useMemo(() => {
    const options = [{ value: "", label: "Whole batch" }];
    for (const { preparation } of sheet.preparations) {
      options.push({ value: `solution_preparation_id:${preparation.id}`, label: `Preparation ${preparation.preparation_code}` });
    }
    for (const { execution } of sheet.executions) {
      options.push({ value: `process_execution_id:${execution.id}`, label: `Execution ${execution.execution_code}` });
    }
    for (const substrate of sheet.substrates) {
      options.push({ value: `substrate_id:${substrate.id}`, label: `Substrate ${substrate.substrate_code}` });
    }
    for (const device of sheet.devices) {
      options.push({ value: `device_id:${device.id}`, label: `Device ${device.device_code}` });
    }
    for (const condition of sheet.conditions) {
      options.push({ value: `condition_id:${condition.id}`, label: `Condition ${condition.condition_code}` });
    }
    return options;
  }, [sheet]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        category,
        severity,
        deviation_type: deviationType,
        description: description.trim(),
      };
      if (target) {
        const [field, id] = target.split(":", 2);
        payload[field] = Number(id);
      }
      payload.planned_value = parseJsonField("Planned value", planned);
      payload.actual_value = parseJsonField("Actual value", actual);
      await onSubmit(payload);
      setCategory("process");
      setSeverity("warning");
      setDeviationType("general");
      setTarget("");
      setDescription("");
      setPlanned("");
      setActual("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record the deviation.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="run-sheet-form deviation-form" onSubmit={(event) => void submit(event)}>
      <label className="form-field">
        <span className="form-field__label">Category</span>
        <select className="text-input" data-deviation-category="true" value={category} onChange={(event) => setCategory(event.target.value)}>
          {["process", "material", "equipment", "substrate", "device", "operator", "other"].map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </label>
      <label className="form-field">
        <span className="form-field__label">Severity</span>
        <select className="text-input" data-deviation-severity="true" value={severity} onChange={(event) => setSeverity(event.target.value)}>
          {["info", "warning", "error", "critical"].map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </label>
      <label className="form-field">
        <span className="form-field__label">Type</span>
        <select className="text-input" data-deviation-type-select="true" value={deviationType} onChange={(event) => setDeviationType(event.target.value)}>
          <option value="general">general</option>
          <option value="fabrication_shortfall">fabrication_shortfall</option>
          <option value="measurement_shortfall">measurement_shortfall</option>
        </select>
      </label>
      <label className="form-field">
        <span className="form-field__label">Target</span>
        <select className="text-input" data-deviation-target="true" value={target} onChange={(event) => setTarget(event.target.value)}>
          {targets.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </label>
      <label className="form-field">
        <span className="form-field__label">Description</span>
        <textarea className="text-input" data-deviation-description="true" required maxLength={5000} value={description} onChange={(event) => setDescription(event.target.value)} />
      </label>
      <label className="form-field">
        <span className="form-field__label">Planned value (JSON)</span>
        <textarea className="text-input" data-deviation-planned="true" value={planned} onChange={(event) => setPlanned(event.target.value)} />
      </label>
      <label className="form-field">
        <span className="form-field__label">Actual value (JSON)</span>
        <textarea className="text-input" data-deviation-actual="true" value={actual} onChange={(event) => setActual(event.target.value)} />
      </label>
      <button className="button button--primary" type="submit" data-deviation-submit="true" disabled={submitting || disabled}>
        Record deviation
      </button>
      <InlineFormError message={error} />
    </form>
  );
}
