# M8 rebrand sweep report

## Naming decision

Name **Slotwise** retained; trademark, domain and store checks not formally
run; final naming is the owner's decision before any public launch.

## Clean-room search

The repository was searched case-insensitively for `Calendly`, plus common
calendar-product phrases (`schedule time`, `book a time`, `scheduling link`,
`meeting link`, `easy scheduling`, and `set your availability`) across source,
tests, fixtures, seeds, metadata and documentation.

### Every `Calendly` hit

| File | Line | Classification | Action |
|---|---:|---|---|
| `AGENTS.md` | 6 | Repository clean-room instruction: do not copy Calendly code/copy/logos/fonts/icons/palette | Retained as the documented reference list |
| `AGENTS.md` | 17 | Repository clean-room instruction: no Calendly assets | Retained as the documented reference list |

There are **zero runtime, UI, metadata, seed, fixture or test hits**. The two
remaining hits are required repository policy, not copied product content.
The phrase search found only domain-neutral scheduling terms used to describe
Slotwise requirements and tests; no copied brand tagline or product copy was
identified.

## Delivered assets

- `apps/web/public/slotwise-logo.svg`: original geometric open-slot mark and
  wordmark; dark-mode media styling; scalable 1024px viewBox.
- `apps/web/public/slotwise-favicon.svg`: compact mark designed for 16px use.
- `apps/web/public/slotwise-og.svg`: original 1200×630 social preview artwork.
- `apps/web/index.html`: title, description, theme color, Open Graph, Twitter,
  favicon and image metadata.
- `apps/web/src/components/Shell.tsx`: branded, keyboard-focusable Slotwise
  home link on S01–S11 shell screens.

## Token sweep

S01–S11 were reviewed against `apps/web/tailwind.config.ts`: the documented
background, surface, border, text, muted text, accent, danger, success, warning,
spacing, typography and radius tokens remain the source of truth. No copied
palette, font, icon set or external logo was introduced. The only raw color in
the existing CSS is the documented accent focus outline; the new assets use the
same original accent/success token values.

## Evidence

The screenshot run writes one real browser capture per S01–S11 at 390px and
1440px to `docs/screenshots/`. Automated axe, contrast, responsive and E2E
checks are re-run after the captures.
