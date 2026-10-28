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
  }),
);

app.use(express.json({ limit: "64kb" }));
app.use(cookieParser());
app.use(pinoHttp({ enabled: process.env.NODE_ENV !== "test" }));
app.use(issueCsrf);
app.use(loadSession as any);

app.get("/health", (_req, res) => res.json({ status: "ok", service: "slotwise-api", version: "0.0.0" }));
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
