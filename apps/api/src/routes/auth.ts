import { Router } from "express";
import { z } from "zod";
import { register, verifyEmail, login, logout, getSessionUser, requestPasswordReset, resetPassword } from "../services/authService.js";
import { Errors } from "../lib/errors.js";
import { rateLimit } from "../middleware/rateLimit.js";
import { csrfProtect } from "../middleware/csrf.js";

const router: Router = Router();

/**
 * CSRF bootstrap: a harmless GET that makes `issueCsrf` hand out the
 * double-submit cookie. The SPA calls this before its first mutation.
 */
router.get("/csrf", (_req, res) => {
  res.json({ ok: true });
});

const loginLimiter = rateLimit({
  name: "login",
  windowMs: 15 * 60_000,
  max: 10,
  key: (req) => String((req.body as { email?: string } | undefined)?.email ?? "").toLowerCase(),
});
const registerLimiter = rateLimit({ name: "register", windowMs: 60 * 60_000, max: 20 });

const registerSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

router.post("/register", registerLimiter, csrfProtect, async (req, res, next) => {
  try {
    const parsed = registerSchema.safeParse(req.body);
    if (!parsed.success) throw parsed.error;
    const result = await register(parsed.data.email, parsed.data.password);
    res.status(201).json(result);
  } catch (e) {
    next(e);
  }
});

router.post("/verify-email", csrfProtect, async (req, res, next) => {
  try {
    const token = z.string().min(1).parse(req.body?.token);
    await verifyEmail(token);
    res.json({ ok: true });
  } catch (e) {
    next(e);
  }
});

router.post("/login", loginLimiter, csrfProtect, async (req, res, next) => {
  try {
    const parsed = loginSchema.safeParse(req.body);
    if (!parsed.success) throw parsed.error;
    const { rawToken, user } = await login(parsed.data.email, parsed.data.password);
    res.cookie("session", rawToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 1000 * 60 * 60 * 24 * 14,
      path: "/",
    });
    res.json({ id: user.id, email: user.email, role: user.role, emailVerified: !!user.emailVerifiedAt });
  } catch (e) {
    next(e);
  }
});

router.post("/logout", csrfProtect, async (req, res, next) => {
  try {
    await logout(req.cookies?.session);
    res.clearCookie("session", { path: "/" });
    res.status(204).send();
  } catch (e) {
    next(e);
  }
});

router.get("/me", async (req, res, next) => {
  try {
    const user = await getSessionUser(req.cookies?.session);
    if (!user) throw Errors.unauthorized();
    res.json({ id: user.id, email: user.email, role: user.role, emailVerified: !!user.emailVerifiedAt });
  } catch (e) {
    next(e);
  }
});

router.post("/password-reset/request", csrfProtect, async (req, res, next) => {
  try {
    const email = z.string().email().parse(req.body?.email);
    await requestPasswordReset(email);
    res.json({ ok: true });
  } catch (e) {
    next(e);
  }
});

router.post("/password-reset/confirm", csrfProtect, async (req, res, next) => {
  try {
    const body = z.object({ token: z.string().min(1), password: z.string().min(8) }).parse(req.body);
    await resetPassword(body.token, body.password);
    res.json({ ok: true });
  } catch (e) {
    next(e);
  }
});

export default router;
