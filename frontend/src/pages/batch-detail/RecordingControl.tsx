import type { ReactNode } from "react";

interface RecordingControlProps {
  value: string;
  editor: ReactNode;
  onChange: (value: string) => void;
}

export function RecordingControl({ value, editor, onChange }: RecordingControlProps) {
  return (
    <div className="run-sheet-recording">
      <label className="form-field">
        <span className="form-field__label">Actual recording</span>
        <select
          className="text-input"
          data-actual-mode="true"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Not recorded yet</option>
          <option value="copied_from_plan">Recorded as planned</option>
          <option value="entered">Record adjusted parameters</option>
        </select>
      </label>
      {value === "entered" && editor}
    </div>
  );
}
