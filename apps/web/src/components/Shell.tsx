import { ReactNode } from "react";

type Props = { title: string; subtitle?: string; children?: ReactNode };

export function Shell({ title, subtitle, children }: Props) {
  return (
    <main className="mx-auto max-w-dashboard px-4 py-8">
      <header className="mb-6">
        <a href="/login" aria-label="Slotwise home" className="mb-5 inline-flex items-center rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
          <img src="/slotwise-logo.svg" alt="Slotwise" className="h-8 w-auto" />
        </a>
        <h1 className="text-h1 font-semibold text-text">{title}</h1>
        {subtitle && <p className="mt-2 text-body text-text-muted">{subtitle}</p>}
      </header>
      <section className="rounded-lg border border-border bg-surface p-6 shadow-sm">
        {children ?? <p className="text-text-muted">Shell placeholder — content coming in later milestones.</p>}
      </section>
    </main>
  );
}
