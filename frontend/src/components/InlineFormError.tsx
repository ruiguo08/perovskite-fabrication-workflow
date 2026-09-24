interface InlineFormErrorProps {
  message: string | null;
}

export function InlineFormError({ message }: InlineFormErrorProps) {
  return message ? (
    <p className="inline-form-error" role="alert">
      {message}
    </p>
  ) : null;
}
