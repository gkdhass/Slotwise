import "dotenv/config";
import { deleteHostAccount, deleteInviteeData } from "../src/services/accountDeletion.js";
import { prisma } from "../src/lib/prisma.js";

/**
 * Operator-run deletion path (docs/PRIVACY.md).
 *
 *   pnpm --filter @slotwise/api delete:account -- --host owner@example.com
 *   pnpm --filter @slotwise/api delete:account -- --invitee someone@example.com
 *   add --dry-run to report what would be deleted without writing.
 *
 * There is no self-service "delete my account" screen in this MVP: the owner
 * performs the request through support and this script executes it. It prints
 * counts only — never the data it removed.
 */
const args = process.argv.slice(2);
const value = (name: string): string | undefined => {
  const i = args.indexOf(`--${name}`);
  return i === -1 ? undefined : args[i + 1];
};
const dryRun = args.includes("--dry-run");

async function main() {
  const host = value("host");
  const invitee = value("invitee");

  if ((!host && !invitee) || (host && invitee)) {
    console.error("usage: delete:account --host <email> | --invitee <email> [--dry-run]");
    process.exit(2);
  }

  const email = (host ?? invitee) as string;
  const result = host
    ? await deleteHostAccount(email, { dryRun })
    : await deleteInviteeData(email, { dryRun });

  if (!result.found) {
    console.log(JSON.stringify({ target: host ? "host" : "invitee", found: false, dryRun }));
    return;
  }

  console.log(
    JSON.stringify({
      target: host ? "host" : "invitee",
      found: true,
      dryRun,
      deleted: {
        users: result.users,
        eventTypes: result.eventTypes,
        bookings: result.bookings,
        outboxJobs: result.outboxJobs,
        sessions: result.sessions,
      },
    }),
  );
}

main()
  .catch((e) => {
    console.error(`deletion failed: ${(e as Error).message}`);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
