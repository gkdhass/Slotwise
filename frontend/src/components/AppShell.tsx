import type { ReactNode } from "react";

import { SlotwiseMark } from "./SlotwiseMark";

const mode = import.meta.env.MODE.toUpperCase();

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <header className="bg-navy text-white">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <SlotwiseMark />
            <div>
              <p className="text-sm font-bold tracking-wide">Slotwise</p>
              <p className="text-xs text-pale-cyan/80">Organizational Threat Identification</p>
            </div>
          </div>
          <span
            className="rounded-full border border-teal/50 bg-deep-blue px-3 py-1 text-xs font-semibold uppercase tracking-widest text-pale-cyan"
            aria-label={`Environment: ${mode}`}
          >
            {mode}
          </span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">{children}</main>

      <footer className="border-t border-navy/10 bg-white/60">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-2 px-6 py-4 text-xs text-muted">
          <span>Module A · cyber events core</span>
          <span>Response actions are simulated and require human approval.</span>
        </div>
      </footer>
    </div>
  );
}
