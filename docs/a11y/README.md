# Contrast audit artefacts (generated, not versioned)

`contrast-390.json` and `contrast-1440.json` in this directory are written by
`tests/e2e/a11y.spec.ts` on every run. They are deliberately **not committed**:
each run seeds a fresh database, so the only thing that changes between runs is
a set of random booking UUIDs (see `docs/REPO_REVIEW.md`). Committing them
produced meaningless churn.

To produce them locally:

```bash
pnpm test:e2e -- a11y.spec.ts
```

The pass/fail signal is the test itself (axe violations and WCAG 2.2 AA contrast
ratios are asserted in the spec), not the JSON file. `docs/TEST_REPORT.md` and
`docs/TRACEABILITY.md` still reference the files as evidence that the audit
runs; the evidence is the test result plus the file produced on the machine
that ran it.
