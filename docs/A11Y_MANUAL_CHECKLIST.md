# Slotwise manual accessibility checklist

**Purpose:** owner-run WCAG 2.2 AA and NVDA sanity pass for NFR-02. Automated
axe, contrast, keyboard-loop and reflow checks do not replace this checklist.

## Test setup

- [ ] Windows display scaling noted: `____%`; browser: `________`, version `____`.
- [ ] NVDA version: `________`; speech mode: Browse + Focus tested.
- [ ] Test date/time: `____`; tester: `________________`.
- [ ] Run the app against the seeded E2E data and use a fresh browser session.
- [ ] No mouse used for the keyboard checks except to start/reset the test.

## Keyboard and focus — every screen S01–S11

- [ ] `Tab` reaches every actionable control in a logical visual order.
- [ ] `Shift+Tab` reverses the order; no focus is lost or trapped outside a modal.
- [ ] Focus indicator is visible against the background at every stop.
- [ ] Buttons activate with `Enter` and `Space`; links activate with `Enter`.
- [ ] There is no keyboard-only dead end, horizontal scroll, or focus on hidden content.
- [ ] Error/success/status messages are announced or discoverable without moving focus.

## Screen-by-screen pass

For each row, tab through the complete screen and record the first problem (or
write `Pass`). Do not mark a row passed solely because axe is clean.

| Screen | Route / flow | Labels, order, errors, announcement, keyboard result | Result |
|---|---|---|---|
| S01 | Sign in / register | Email/password labels; submit result; switch mode | ☐ Pass ☐ Issue |
| S02 | Dashboard | Page heading; event actions; empty/loading states | ☐ Pass ☐ Issue |
| S03 | Event editor | Required fields; validation text; save result | ☐ Pass ☐ Issue |
| S04 | Availability | Day/time controls; add/remove; validation | ☐ Pass ☐ Issue |
| S05 | Preview/publish | Publish state and confirmation feedback | ☐ Pass ☐ Issue |
| S06 | Public event | Heading, event details, location and next action | ☐ Pass ☐ Issue |
| S07 | Slot selector | Date navigation, selected slot, unavailable/loading state | ☐ Pass ☐ Issue |
| S08 | Invitee details | All labels, required errors, submit result | ☐ Pass ☐ Issue |
| S09 | Confirmation | Booking reference, next steps, no silent failure | ☐ Pass ☐ Issue |
| S10 | Manage booking | Cancel/reschedule controls; modal; Escape; focus return | ☐ Pass ☐ Issue |
| S11 | Booking list | Table/list headings, status, filters and empty state | ☐ Pass ☐ Issue |

## NVDA booking loop

- [ ] Start at S06 and use NVDA `H`/`Shift+H` to move through headings.
- [ ] Use `F`/`Shift+F` and `Tab` to find the slot/date controls on S07.
- [ ] Select a slot without a mouse; NVDA announces the selected state.
- [ ] On S08, NVDA reads every label, required state and validation message.
- [ ] Submit the booking and confirm S09's heading and booking result are announced.
- [ ] Open S10's cancel dialog; focus enters the dialog, Escape closes it, and
  focus returns to the invoking control.
- [ ] Confirm no raw UUID, duplicate label, unexplained “click here”, or silent
  loading/error state is exposed to the user.

## Findings and sign-off

| ID | Screen / step | Finding and reproduction | Severity | Fix / issue link | Retest |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |
| | | | | | |

**Overall result:** ☐ Pass — no unresolved critical/serious issue  ☐ Partial  ☐ Fail

**Tester signature:** ____________________  **Date:** __________
