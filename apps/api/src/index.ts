import "dotenv/config";
import express from "express";
import type { Express } from "express";
import helmet from "helmet";
import cors from "cors";
import cookieParser from "cookie-parser";
import { pinoHttp } from "pino-http";
import { requestId } from "./middleware/requestId.js";
import { loadSession, requireAuth } from "./middleware/auth.js";
import { issueCsrf, csrfProtect } from "./middleware/csrf.js";
import { errorHandler } from "./middleware/errorHandler.js";
import { assertProductionSafety, corsAllowList } from "./lib/config.js";
import { logger } from "./lib/logger.js";
import { prisma } from "./lib/prisma.js";
import authRoutes from "./routes/auth.js";
import eventTypeRoutes from "./routes/eventTypes.js";
import publicRoutes from "./routes/public.js";
import bookingRoutes from "./routes/bookings.js";
import manageRoutes from "./routes/manage.js";

// Fail fast before any listener is created.
assertProductionSafety();

const app: Express = express();
app.set("trust proxy", 1);

app.use(requestId as any);
app.use(
  helmet({
    referrerPolicy: { policy: "no-referrer" },
  }),
);

const allowed = corsAllowList();
app.use(
  cors({
    origin(origin, cb) {
      // Same-origin/no-Origin requests (curl, server-to-server) are allowed;
      // browser cross-origin requests must match the allow-list exactly.
      if (!origin || allowed.includes(origin)) return cb(null, true);
      return cb(null, false);
    },
    credentials: true,
    methods: ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allowedHeaders: ["Content-Type", "X-CSRF-Token", "X-Request-Id", "X-Worker-Secret"],
    // Let browser code read the correlation id for bug reports.
    exposedHeaders: ["X-Request-Id"],
  }),
);

app.use(express.json({ limit: "64kb" }));
app.use(cookieParser());
app.use(
  pinoHttp({
    logger,
    // The id assigned by the requestId middleware above, not a second one.
    genReqId: (req) => (req as { id?: string }).id ?? "unknown",
    // Health probes would otherwise dominate the log on a busy host.
    autoLogging: { ignore: (req) => req.url === "/health" || req.url === "/health/ready" },
  }),
);
app.use(issueCsrf);
app.use(loadSession as any);

/**
 * Liveness: the process is up and serving. Deliberately does not touch the
 * database, so a platform health check does not fail because of a slow query.
 */
app.get("/health", (_req, res) => res.json({ status: "ok", service: "slotwise-api", version: "0.0.0" }));

/**
 * Readiness: the process can serve real traffic, which for this API means the
 * database answers. Returns 503 so a load balancer takes the instance out.
 */
app.get("/health/ready", async (_req, res) => {
  try {
    await prisma.$queryRaw`SELECT 1`;
    res.json({ status: "ok", database: "ok" });
  } catch (e) {
    logger.error({ err: (e as Error).message }, "readiness check failed");
    res.status(503).json({ status: "unavailable", database: "unreachable" });
  }
});

app.get("/api/v1/health", (_req, res) => res.json({ status: "ok" }));

app.use("/api/v1/auth", authRoutes);
app.use("/api/v1/event-types", requireAuth as any, csrfProtect, eventTypeRoutes);
app.use("/api/v1/public", publicRoutes);
app.use("/api/v1/bookings", requireAuth as any, csrfProtect, bookingRoutes);
app.use(
  "/api/v1/manage",
  (_req, res, next) => {
    // Manage links are bearer-token URLs: never leak them via Referer.
    res.setHeader("Referrer-Policy", "no-referrer");
    res.setHeader("Cache-Control", "no-store");
    next();
  },
  csrfProtect,
  manageRoutes,
);

app.post("/api/v1/worker/run-outbox", async (req, res) => {
  if (!process.env.WORKER_SECRET || req.get("x-worker-secret") !== process.env.WORKER_SECRET) {
    return res
      .status(401)
      .json({ error: { code: "UNAUTHORIZED", message: "Unauthorized.", requestId: (req as any).id ?? "", fieldErrors: {} } });
  }
  const { processOneBatch } = await import("./worker/emailWorker.js");
  const n = await processOneBatch();
  res.json({ processed: n });
});

app.use(errorHandler as any);

const port = Number(process.env.PORT ?? 4000);
if (process.env.NODE_ENV !== "test") {
  app.listen(port, () => {
    console.log(`slotwise-api listening on ${port}`);
  });
}

export default app;
