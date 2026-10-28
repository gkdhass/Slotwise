import { prisma } from "../lib/prisma.js";
import { hashPassword, verifyPassword, hashToken, randomToken } from "../lib/hash.js";
import { sendEmail } from "../lib/email.js";
import { Errors } from "../lib/errors.js";

const SESSION_TTL_MS = 1000 * 60 * 60 * 24 * 14;
const VERIFY_TTL_MS = 1000 * 60 * 60 * 24;

/**
 * The seven-table schema has no dedicated token table, so verification and
 * password-reset tokens are rows in `sessions` distinguished by a prefix on the
 * raw token. That prefix is the only thing that tells a single-use email token
 * apart from a 14-day session cookie, so it is enforced in both directions:
 * an email token can never authenticate a request, and a session cookie can
 * never be spent as a reset token.
 */
const VERIFY_PREFIX = "verify:";
const RESET_PREFIX = "reset:";

function isEmailToken(rawToken: string | undefined): boolean {
  return !!rawToken && (rawToken.startsWith(VERIFY_PREFIX) || rawToken.startsWith(RESET_PREFIX));
}

export async function register(email: string, password: string) {
  const existing = await prisma.user.findUnique({ where: { email } });
  if (existing) throw Errors.validation("Email already registered.", { email: "Already in use" });
  const passwordHash = await hashPassword(password);
  const user = await prisma.user.create({
    data: { email, passwordHash, role: "owner" },
  });
  // Email verification token. The 7-table schema has no dedicated table, so the
  // hash lives in `sessions` and the raw token is prefixed `verify:` to keep it
  // distinguishable from a real session token (see docs/DECISIONS.md).
  const raw = randomToken();
  const verifyRaw = `${VERIFY_PREFIX}${raw}`;
  await prisma.session.create({
    data: {
      userId: user.id,
      tokenHash: hashToken(verifyRaw),
      expiresAt: new Date(Date.now() + VERIFY_TTL_MS),
    },
  });
  const link = `${process.env.APP_BASE_URL ?? "http://localhost:5173"}/verify-email?token=${verifyRaw}`;
  await sendEmail({
    to: email,
    subject: "Verify your Slotwise email",
    text: `Verify your email: ${link}`,
    html: `<p>Verify your email: <a href="${link}">${link}</a></p>`,
  });
  return { id: user.id, email: user.email, emailVerified: false };
}

export async function verifyEmail(rawToken: string) {
  if (!rawToken.startsWith(VERIFY_PREFIX)) throw Errors.validation("Invalid or expired token.");
  const tokenHash = hashToken(rawToken);
  const session = await prisma.session.findUnique({ where: { tokenHash } });
  if (!session || session.revokedAt || session.expiresAt < new Date()) throw Errors.validation("Invalid or expired token.");
  const user = await prisma.user.update({
    where: { id: session.userId },
    data: { emailVerifiedAt: new Date() },
  });
  await prisma.session.update({ where: { id: session.id }, data: { revokedAt: new Date() } });
  return user;
}

export async function login(email: string, password: string) {
  const user = await prisma.user.findUnique({ where: { email } });
  // A deleted account must be indistinguishable from a wrong password: issuing a
  // cookie that `getSessionUser` rejects would report success and then log the
  // user out on the next request.
  if (!user || user.deletedAt) throw Errors.unauthorized();
  const ok = await verifyPassword(user.passwordHash, password);
  if (!ok) throw Errors.unauthorized();
  const raw = randomToken();
  const session = await prisma.session.create({
    data: {
      userId: user.id,
      tokenHash: hashToken(raw),
      expiresAt: new Date(Date.now() + SESSION_TTL_MS),
    },
  });
  return { rawToken: raw, sessionId: session.id, user };
}

export async function logout(rawToken: string | undefined) {
  if (!rawToken) return;
  await prisma.session.updateMany({
    where: { tokenHash: hashToken(rawToken), revokedAt: null },
    data: { revokedAt: new Date() },
  });
}

export async function getSessionUser(rawToken: string | undefined) {
  if (!rawToken) return null;
  // A verification or reset token is a row in the same table; it is not a session.
  if (isEmailToken(rawToken)) return null;
  const session = await prisma.session.findUnique({ where: { tokenHash: hashToken(rawToken) } });
  if (!session || session.revokedAt || session.expiresAt < new Date()) return null;
  const user = await prisma.user.findUnique({ where: { id: session.userId } });
  if (!user || user.deletedAt) return null;
  return user;
}

export async function requestPasswordReset(email: string) {
  const user = await prisma.user.findUnique({ where: { email } });
  if (!user) return; // do not disclose
  const raw = `${RESET_PREFIX}${randomToken()}`;
  await prisma.session.create({
    data: { userId: user.id, tokenHash: hashToken(raw), expiresAt: new Date(Date.now() + VERIFY_TTL_MS) },
  });
  const link = `${process.env.APP_BASE_URL ?? "http://localhost:5173"}/reset-password?token=${raw}`;
  await sendEmail({ to: email, subject: "Reset your Slotwise password", text: `Reset: ${link}`, html: `<p>Reset: ${link}</p>` });
}

export async function resetPassword(rawToken: string, newPassword: string) {
  if (!rawToken.startsWith(RESET_PREFIX)) throw Errors.validation("Invalid or expired token.");
  const session = await prisma.session.findUnique({ where: { tokenHash: hashToken(rawToken) } });
  if (!session || session.revokedAt || session.expiresAt < new Date()) throw Errors.validation("Invalid or expired token.");
  const passwordHash = await hashPassword(newPassword);
  await prisma.user.update({ where: { id: session.userId }, data: { passwordHash } });
  await prisma.session.update({ where: { id: session.id }, data: { revokedAt: new Date() } });
  // revoke all sessions
  await prisma.session.updateMany({ where: { userId: session.userId, revokedAt: null }, data: { revokedAt: new Date() } });
}