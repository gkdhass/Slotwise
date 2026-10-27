export type EmailMessage = { to: string; subject: string; html: string; text?: string };

export async function sendEmail(msg: EmailMessage): Promise<void> {
  const provider = process.env.EMAIL_PROVIDER ?? "console";
  if (provider === "console" || !process.env.RESEND_API_KEY) {
    // Dev transport: log the link/content instead of sending.
    console.log(`[email:console] to=${msg.to} subject="${msg.subject}"`);
    console.log(msg.text ?? msg.html);
    return;
  }
  // Resend (production) - lazy import to avoid requiring the dep in dev
  const resendMod: any = await import("resend" as any);
  const resend = new resendMod.Resend(process.env.RESEND_API_KEY);
  await resend.emails.send({
    from: process.env.EMAIL_FROM ?? "Slotwise <no-reply@example.com>",
    to: msg.to,
    subject: msg.subject,
    html: msg.html,
    text: msg.text,
  });
}