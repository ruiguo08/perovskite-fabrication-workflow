import { useState } from "react";
import { FormField } from "./FormField";

interface JsonObjectFieldProps {
  id: string;
  label: string;
  value: string;
  hint?: string;
  disabled?: boolean;
  onTextChange: (value: string) => void;
  onValidChange: (value: Record<string, unknown>) => void;
  onValidityChange?: (valid: boolean) => void;
  validateObject?: (value: Record<string, unknown>) => string | null;
}

function parseJsonObject(value: string): {
  parsed: Record<string, unknown> | null;
  error: string | null;
} {
  try {
    const parsed: unknown = JSON.parse(value);
    if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
      return { parsed: null, error: "Specification must be a JSON object." };
    }
    return { parsed: parsed as Record<string, unknown>, error: null };
  } catch {
    return { parsed: null, error: "Specification must be valid JSON." };
  }
}

export function JsonObjectField({
  id,
  label,
  value,
  hint = "Enter a JSON object. Use {} when no structured specification is needed.",
  disabled,
  onTextChange,
  onValidChange,
  onValidityChange,
  validateObject,
}: JsonObjectFieldProps) {
  const [error, setError] = useState<string | null>(null);

  function handleChange(nextValue: string) {
    onTextChange(nextValue);
    const result = parseJsonObject(nextValue);
    const semanticError = result.parsed === null ? null : validateObject?.(result.parsed) ?? null;
    const nextError = result.error ?? semanticError;
    setError(nextError);
    const valid = nextError === null && result.parsed !== null;
    onValidityChange?.(valid);
    if (valid) {
      onValidChange(result.parsed!);
    }
  }

  return (
    <FormField label={label} htmlFor={id} error={error} hint={hint}>
      <textarea
        id={id}
        className="text-input json-object-field mono"
        rows={3}
        spellCheck={false}
        disabled={disabled}
        value={value}
        aria-describedby={error ? `${id}-error` : `${id}-hint`}
        aria-invalid={error ? "true" : undefined}
        onChange={(event) => handleChange(event.target.value)}
      />
    </FormField>
  );
}
