import express, { type Express } from "express";
import helmet from "helmet";
import cors from "cors";
import cookieParser from "cookie-parser";
import { pinoHttp } from "pino-http";

const app: Express = express();

app.use(helmet());
app.use(cors({ origin: process.env.APP_BASE_URL ?? "http://localhost:5173", credentials: true }));
app.use(express.json());
app.use(cookieParser());
app.use(pinoHttp());

app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "slotwise-api", version: "0.0.0" });
});

app.get("/api/v1/health", (_req, res) => {
  res.json({ status: "ok" });
});

const port = Number(process.env.PORT ?? 4000);
if (process.env.NODE_ENV !== "test") {
  app.listen(port, () => {
    console.log(`slotwise-api listening on ${port}`);
  });
}

export default app;