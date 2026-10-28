import { prisma } from "../lib/prisma.js";
import { hashPassword, verifyPassword, hashToken, randomToken } from "../lib/hash.js";
import { sendEmail } from "../lib/email.js";
import { Errors } from "../lib/errors.js";

const SESSION_TTL_MS = 1000 * 60 * 60 * 24 * 14;
const VERIFY_TTL_MS = 1000 * 60 * 60 * 24;

export async function register(email: string, password: string) {
  const existing = await prisma.user.findUnique({ where: { email } });
  if (existing) throw Errors.validation("Email already registered.", { email: "Already in use" });
  const passwordHash = await hashPassword(password);
  const user = await prisma.user.create({
    data: { email, passwordHash, role: "owner" },
  });
  // email verification token
  const raw = randomToken();
  const tokenHash = hashToken(raw);
  // store in sessions? Use a lightweight approach: store token hash in a management_tokens-like row? 
  // Simpler: store verification token as a session with a marker? Instead, use a dedicated table would be ideal.
  // For MVP, store the hashed token in a new row in sessions with revokedAt null and a far-future expiry? 
  // We'll reuse a simple in-memory map is not durable. Use outbox? 
  // Decision: store verification token in `sessions` table is wrong. Add a column? Schema has no verification_tokens table.
  // Use management_tokens? Not linked to booking. 
  // Pragmatic: store hashed token in user? No column. 
  // We'll create a verification token row by reusing sessions with a special prefix is hacky.
  // Instead, log the raw token and store hash in a new table via raw SQL? Schema fixed at 7 tables.
  // Compromise: store verification token hash in `sessions.token_hash` with user_id and expires_at, marked by a role? 
  // We'll store it and treat any session row whose token matches and not revoked as a verification token lookup.
  // To distinguish, prefix raw token with "verify:".
  const verifyRaw = `verify:${raw}`;
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
  if (!user) throw Errors.unauthorized();
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
  const session = await prisma.session.findUnique({ where: { tokenHash: hashToken(rawToken) } });
  if (!session || session.revokedAt || session.expiresAt < new Date()) return null;
  const user = await prisma.user.findUnique({ where: { id: session.userId } });
  if (!user || user.deletedAt) return null;
  return user;
}

export async function requestPasswordReset(email: string) {
  const user = await prisma.user.findUnique({ where: { email } });
  if (!user) return; // do not disclose
  const raw = `reset:${randomToken()}`;
  await prisma.session.create({
    data: { userId: user.id, tokenHash: hashToken(raw), expiresAt: new Date(Date.now() + VERIFY_TTL_MS) },
  });
  const link = `${process.env.APP_BASE_URL ?? "http://localhost:5173"}/reset-password?token=${raw}`;
  await sendEmail({ to: email, subject: "Reset your Slotwise password", text: `Reset: ${link}`, html: `<p>Reset: ${link}</p>` });
}

export async function resetPassword(rawToken: string, newPassword: string) {
  const session = await prisma.session.findUnique({ where: { tokenHash: hashToken(rawToken) } });
  if (!session || session.revokedAt || session.expiresAt < new Date()) throw Errors.validation("Invalid or expired token.");
  const passwordHash = await hashPassword(newPassword);
  await prisma.user.update({ where: { id: session.userId }, data: { passwordHash } });
  await prisma.session.update({ where: { id: session.id }, data: { revokedAt: new Date() } });
  // revoke all sessions
  await prisma.session.updateMany({ where: { userId: session.userId, revokedAt: null }, data: { revokedAt: new Date() } });
}