# PRIVACY.md — data, retention and deletion in Slotwise

Scope: the single-host MVP. This document describes what the code actually does;
it is not legal advice, and the owner is the data controller for their own
account and their invitees' booking data.

---

## 1. Roles

- **Host (owner)** — registers an account, publishes event types, sees bookings.
- **Invitee** — books a slot from a public page without creating an account.
- **Operator** — whoever runs the deployment. Executes deletion requests (§6) and
  holds the backups (§5).

---

## 2. What is stored

| Data | Where | Why | Notes |
| --- | --- | --- | --- |
| Host email | `users.email` | Sign-in, verification, notifications | Unique. |
| Password | `users.password_hash` | Authentication | Argon2id hash only; the plaintext is never stored or logged. |
| Email-verification token | `sessions.token_hash` (prefix `verify:`) | Prove address ownership | SHA-256 hash of the token; raw value only in the emailed link. |
| Session token | `sessions.token_hash` | Keep the host signed in | SHA-256 hash; raw value only in the cookie. |
| Event type: title, description, slug, duration, location text, time zone, availability | `event_types`, `availability_rules` | Publish a bookable page | Public by design once published. |
| Invitee name, email, optional note, time zone | `bookings` | Create and manage the appointment | The only invitee data collected. |
| Booking start/end (UTC), status | `bookings` | Scheduling and conflict checks | Timestamps only. |
| Management token | `management_tokens.token_hash` | Let the invitee cancel/reschedule without an account | SHA-256 hash; 30-day expiry. |
| Queued email payload | `outbox_jobs.payload` | Send confirmations/cancellations reliably | Contains the recipient address and booking id; deleted with the booking. |

**Not collected:** no analytics, no advertising or third-party scripts, no
fingerprinting, no IP-based profiling, no payment data (payments are disabled,
D-08), no invitee account, no address book access.

---

## 3. Cookies

| Cookie | HttpOnly | SameSite | Secure | Lifetime | Purpose |
| --- | --- | --- | --- | --- | --- |
| `session` | yes | Lax | yes in production | 14 days | Signed-in host session (hashed token server-side). |
| `csrf_token` | no (read by the SPA to echo in `x-csrf-token`) | Lax | yes in production | session | Double-submit CSRF protection. |

No marketing or analytics cookies exist, so no cookie banner is required for them.

---

## 4. Logs

Structured JSON request logs are written for operations and abuse detection. They
contain the request id, method, URL path, status code and timing. They **do not**
contain request bodies, passwords, cookies, CSRF tokens, worker secrets or
management tokens: those paths are redacted to `[Redacted]`, and error reports
mask long token-like path segments before logging or forwarding to an external
monitor (`apps/api/src/lib/logger.ts`, `apps/api/src/lib/errorMonitor.ts`).

Log retention is the host platform's log retention; this MVP does not export or
archive logs itself.

---

## 5. Retention

| Data | Retention | Enforced by |
| --- | --- | --- |
| Session | 14 days, or until sign-out/revocation | `SESSION_TTL_MS`, `sessions.expires_at` |
| Email-verification token | 24 hours | `VERIFY_TTL_MS` |
| Management token | 30 days | `management_tokens.expires_at` |
| Booking + its outbox job | Until the host deletes the account or the invitee asks for deletion | Deletion path, §6 |
| Canceled booking | Kept as `status = canceled` so the slot history stays truthful; removed with the account | §6 |

Not implemented: an automatic purge job for old canceled bookings. Until one
exists, retention for those rows is "until deleted by the operator".

**Backups** (see `docs/DEPLOYMENT.md` §6) keep a copy of deleted rows until the
backup ages out of the 7-daily-dump window. A deletion request therefore removes
data from the live database immediately and from backups within 7 days.

---

## 6. Deletion path

There is **no self-service "delete my account" screen** in this MVP. Deletion is
an operator action, executed with a script that runs in one transaction and
prints counts only (never the deleted values):

```bash
# what would be removed (no writes)
pnpm --filter @slotwise/api delete:account -- --host owner@example.com --dry-run

# delete a host account and everything belonging to it
pnpm --filter @slotwise/api delete:account -- --host owner@example.com

# delete one invitee's bookings across all hosts
pnpm --filter @slotwise/api delete:account -- --invitee someone@example.com
```

### Host account deletion removes

1. queued email jobs for that host's bookings (they hold the invitee's address),
2. the bookings themselves (which removes their management tokens by cascade),
3. the event types (which removes availability rules by cascade),
4. sessions (including the email-verification token),
5. the user row.

It is transactional: a failure leaves the account untouched. It is idempotent: a
second run reports `found: false`. The address match is case-insensitive. Hosts
are isolated: deleting one account never touches another host's events or
bookings.

Why a script rather than a database cascade: `bookings.user_id` and
`bookings.event_type_id` are `onDelete: Restrict` on purpose, so that no stray
delete can silently wipe a calendar. The deletion order is explicit in
`apps/api/src/services/accountDeletion.ts`.

### Invitee data-subject deletion removes

Every booking made with that email address, across all hosts, plus their queued
email jobs. Event types, availability and host accounts are untouched. The host's
booking list shrinks accordingly — the invitee's name, email, note and time zone
are gone with the row.

### What deletion does not do

- It does not remove the data from backups already taken (§5); those age out.
- It does not delete logs, which never contained the data in the first place.
- It does not notify the other party. If a host cancels, the invitee should be
  told by email before the account is deleted; if an invitee is deleted, the host
  simply sees one fewer booking.

### Verified

`apps/api/tests/integration/accountDeletion.test.ts` (7 tests) proves: the host's
user/event/availability/booking/token/session/outbox rows are all gone; a second
host's data is untouched; unknown addresses report `found: false`; matching is
case-insensitive; `--dry-run` writes nothing; an invitee's bookings are removed
across hosts while the hosts keep their events and other bookings.

---

## 7. Data-subject requests

1. Verify the requester controls the address (reply from it, or confirm through
   the host for invitee data).
2. Run the `--dry-run` command and check the counts look like the requester's data.
3. Run the deletion command; record the returned counts (no personal data) in the
   operator log.
4. Confirm completion to the requester.

**Export is not implemented.** If an export is required, the operator runs a
targeted `psql` query and sends the result over a channel the requester controls.
Documented as a gap rather than claimed as a feature.

---

## 8. Security measures that support these promises

- Argon2id password hashing; session, verification and management tokens stored
  only as SHA-256 hashes.
- Session cookies `HttpOnly`, `SameSite=Lax`, `Secure` in production.
- CSRF double-submit on every mutating request; the bypass is refused at startup
  when `NODE_ENV=production`.
- Management links are bearer-token URLs: `Referrer-Policy: no-referrer` and
  `Cache-Control: no-store` on that route.
- Unknown/expired management tokens return one generic denial, so a token's
  existence cannot be probed.
- Helmet security headers, a CORS allow-list, fixed-window rate limits, and a
  request-size cap of 64 kB.

---

## 9. Changes

Any change to what is collected, or to retention, must be recorded in
`docs/DECISIONS.md` and mirrored here in the same change.
