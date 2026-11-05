# Booking strategy concurrency evaluation

Generated: 2026-11-05T06:39:16.032Z

Profile: **20 trials × 32 concurrent contenders**, same host and overlapping 30-minute slot each trial; race widening sleep: 5 ms. Results are local PostgreSQL measurements, not production capacity claims.

| Strategy | Trials | Mean accepted | Mean rejected | Max confirmed | Violating trials | Mean p95 attempt |
|---|---:|---:|---:|---:|---:|---:|
| check-then-insert | 20 × 32 | 31.9 | 0.1 | 32 | 20/20 | 79.0 ms |
| transactional-check-without-constraint | 20 × 32 | 9.0 | 23.0 | 9 | 20/20 | 84.9 ms |
| exclusion-constraint | 20 × 32 | 1.0 | 31.0 | 1 | 0/20 | 6001.1 ms |

## Interpretation

- **check-then-insert** performs the availability check outside a transaction and is expected to admit overlapping rows under contention.
- **transactional-check-without-constraint** performs the check and insert in one default READ COMMITTED transaction, but without a database serialization or exclusion invariant; the check is still not a lock.
- **exclusion-constraint** relies on PostgreSQL's bookings_no_host_overlap GiST exclusion constraint. Concurrent losers are rejected and no trial may contain more than one confirmed row.

The application route uses the third strategy: it performs friendly pre-checks for UX, then the database constraint is the integrity authority. Re-run with BOOKING_EVAL_TRIALS, BOOKING_EVAL_CONTENDERS, and BOOKING_EVAL_SLEEP_MS to change the profile.
