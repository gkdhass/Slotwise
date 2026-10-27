import { ReactNode } from "react";

type Variant = "error" | "warning" | "success" | "info";

type Props = { variant?: Variant; children: ReactNode; title?: string };

const classes: Record<Variant, string> = {
  error: "border-danger bg-red-50 text-danger",
  warning: "border-warning bg-amber-50 text-warning",
  success: "border-success bg-green-50 text-success",
  info: "border-border bg-bg text-text",
};

export function Alert({ variant = "info", title, children }: Props) {
  return (
    <div role={variant === "error" ? "alert" : "status"} className={`rounded-md border p-3 text-small ${classes[variant]}`}>
      {title && <p className="font-semibold">{title}</p>}
      <div>{children}</div>
    </div>
  );
}