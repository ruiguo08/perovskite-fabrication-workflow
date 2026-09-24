import type { ReactNode } from "react";

interface FormFieldProps {
  label: string;
  htmlFor: string;
  error?: string | null;
  hint?: string;
  required?: boolean;
  children: ReactNode;
}

/**
 * Labeled control wrapper that ties validation errors to the input.
 * The rendered control should set `aria-describedby={`${htmlFor}-error`}`
 * when `error` is present so the message is announced with the field.
 */
export function FormField({
  label,
  htmlFor,
  error,
  hint,
  required,
  children,
}: FormFieldProps) {
  return (
    <div className="form-field">
      <label className="form-field__label" htmlFor={htmlFor}>
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </label>
      {children}
      {error ? (
        <p className="form-field__error" id={`${htmlFor}-error`} role="alert">
          {error}
        </p>
      ) : null}
      {hint && !error ? (
        <p className="form-field__hint" id={`${htmlFor}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}