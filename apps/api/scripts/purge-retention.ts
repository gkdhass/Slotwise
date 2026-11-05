import { prisma } from "../src/lib/prisma.js";
import { purgeExpiredBookings, retentionConfig } from "../src/services/retentionPurge.js";

const config = retentionConfig();
const result = await purgeExpiredBookings({ config });

console.log(
  JSON.stringify({
    event: "retention_purge",
    canceled: result.canceled,
    completed: result.completed,
    total: result.total,
    canceledBefore: result.canceledBefore.toISOString(),
    completedBefore: result.completedBefore.toISOString(),
  }),
);

await prisma.$disconnect();
