import { prisma } from "../lib/prisma.js";

/**
 * Account and invitee data deletion (NFR-04, docs/PRIVACY.md).
 *
 * Why this is a service and not a cascade: `Booking.user` and
 * `Booking.eventType` are `onDelete: Restrict`, deliberately, so that a stray
 * delete can never silently destroy a host's calendar. Removal therefore has to
 * be an explicit, ordered, transactional operation — which is exactly what a
 * deletion request needs anyway.
 *
 * Order matters:
 *   outbox jobs (they carry the invitee's email in the payload)
 *   -> bookings (management tokens cascade from here)
 *   -> event types (availability rules cascade from here)
 *   -> sessions
 *   -> user
 *
 * Everything runs in one transaction: a failure leaves the account untouched
 * rather than half-deleted. `dryRun` reports the same counts without writing.
 */

export type DeletionCounts = {
  found: boolean;
  outboxJobs: number;
  bookings: number;
  eventTypes: number;
  sessions: number;
  users: number;
};

const EMPTY: DeletionCounts = { found: false, outboxJobs: 0, bookings: 0, eventTypes: 0, sessions: 0, users: 0 };

/**
 * Deletes a host account and everything that belongs to it.
 *
 * Booking rows contain the invitee's name, email, optional note and time zone,
 * so they are deleted with the account: the host's own records are the only
 * copy, and keeping them after deletion would contradict the policy.
 */
export async function deleteHostAccount(email: string, opts: { dryRun?: boolean } = {}): Promise<DeletionCounts> {
  const user = await prisma.user.findFirst({
    where: { email: { equals: email.trim(), mode: "insensitive" } },
    select: { id: true },
  });
  if (!user) return { ...EMPTY };

  const bookingIds = (
    await prisma.booking.findMany({ where: { userId: user.id }, select: { id: true } })
  ).map((b) => b.id);

  const counts = {
    outboxJobs: await prisma.outboxJob.count({ where: { bookingId: { in: bookingIds } } }),
    bookings: bookingIds.length,
    eventTypes: await prisma.eventType.count({ where: { userId: user.id } }),
    sessions: await prisma.session.count({ where: { userId: user.id } }),
  };

  if (opts.dryRun) return { found: true, users: 0, ...counts };

  const [outboxJobs, bookings, eventTypes, sessions, users] = await prisma.$transaction([
    prisma.outboxJob.deleteMany({ where: { bookingId: { in: bookingIds } } }),
    prisma.booking.deleteMany({ where: { id: { in: bookingIds } } }),
    prisma.eventType.deleteMany({ where: { userId: user.id } }),
    prisma.session.deleteMany({ where: { userId: user.id } }),
    prisma.user.deleteMany({ where: { id: user.id } }),
  ]);

  return {
    found: true,
    outboxJobs: outboxJobs.count,
    bookings: bookings.count,
    eventTypes: eventTypes.count,
    sessions: sessions.count,
    users: users.count,
  };
}

/**
 * Deletes every booking made by an invitee, across all hosts, for a data-subject
 * request. Event types, availability and the hosts' accounts are untouched.
 */
export async function deleteInviteeData(email: string, opts: { dryRun?: boolean } = {}): Promise<DeletionCounts> {
  const bookings = await prisma.booking.findMany({
    where: { inviteeEmail: { equals: email.trim(), mode: "insensitive" } },
    select: { id: true },
  });
  if (bookings.length === 0) return { ...EMPTY };

  const bookingIds = bookings.map((b) => b.id);
  const outboxJobs = await prisma.outboxJob.count({ where: { bookingId: { in: bookingIds } } });

  if (opts.dryRun) {
    return { found: true, outboxJobs, bookings: bookingIds.length, eventTypes: 0, sessions: 0, users: 0 };
  }

  const [jobs, removed] = await prisma.$transaction([
    prisma.outboxJob.deleteMany({ where: { bookingId: { in: bookingIds } } }),
    prisma.booking.deleteMany({ where: { id: { in: bookingIds } } }),
  ]);

  return {
    found: true,
    outboxJobs: jobs.count,
    bookings: removed.count,
    eventTypes: 0,
    sessions: 0,
    users: 0,
  };
}
