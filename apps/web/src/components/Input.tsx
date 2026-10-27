import { InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
  hint?: string;
};

export function Input({ label, error, hint, id, className = "", ...rest }: Props) {
  const inputId = id ?? `input-${label.toLowerCase().replace(/\s+/g, "-")}`;
  const errorId = `${inputId}-error`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-small font-medium text-text">
        {label}
      </label>
      <input
        id={inputId}
        aria-invalid={!!error}
        aria-describedby={error ? errorId : undefined}
        className={`rounded-md border px-3 py-2 text-body text-text placeholder:text-text-muted focus:outline focus:outline-2 focus:outline-offset-1 focus:outline-accent ${
          error ? "border-danger" : "border-border-input"
        } ${className}`}
        {...rest}
      />
      {hint && !error && <p className="text-caption text-text-muted">{hint}</p>}
      {error && (
        <p id={errorId} role="alert" className="text-caption text-danger">
          {error}
        </p>
      )}
    </div>
  );
}