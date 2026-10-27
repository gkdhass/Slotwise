import { Router } from "express";
import { z } from "zod";
import { register, verifyEmail, login, logout, getSessionUser, requestPasswordReset, resetPassword } from "../services/authService.js";
import { Errors } from "../lib/errors.js";

const router: Router = Router();

const registerSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

router.post("/register", async (req, res, next) => {
  try {
    const parsed = registerSchema.safeParse(req.body);
    if (!parsed.success) throw parsed.error;
    const result = await register(parsed.data.email, parsed.data.password);
    res.status(201).json(result);
  } catch (e) {
    next(e);
  }
});

router.post("/verify-email", async (req, res, next) => {
  try {
    const token = z.string().min(1).parse(req.body?.token);
    await verifyEmail(token);
    res.json({ ok: true });
  } catch (e) {
    next(e);
  }
});

router.post("/login", async (req, res, next) => {
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

router.post("/logout", async (req, res, next) => {
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

router.post("/password-reset/request", async (req, res, next) => {
  try {
    const email = z.string().email().parse(req.body?.email);
    await requestPasswordReset(email);
    res.json({ ok: true });
  } catch (e) {
    next(e);
  }
});

router.post("/password-reset/confirm", async (req, res, next) => {
  try {
    const body = z.object({ token: z.string().min(1), password: z.string().min(8) }).parse(req.body);
    await resetPassword(body.token, body.password);
    res.json({ ok: true });
  } catch (e) {
    next(e);
  }
});

export default router;
