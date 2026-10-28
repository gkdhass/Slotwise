import fs from "node:fs";
import crypto from "node:crypto";

const TEMP = "C:\\Users\\Mohan\\AppData\\Local\\Temp\\neon-url.txt";
const TARGETS = [".env", "apps/api/.env"];

function die(msg) {
  console.log(`REFUSED: ${msg}`);
  process.exit(1);
}

function classify(u) {
  let p;
  try {
    p = new URL(u);
  } catch {
    return "UNPARSEABLE";
  }
  const h = p.hostname;
  if (/^(localhost|127\.0\.0\.1|0\.0\.0\.0|::1)$/.test(h)) return "LOCAL";
  if (/pooler/i.test(h)) return "neon POOLED";
  if (/\.neon\.tech$/i.test(h)) return "neon direct";
  if (/neon/i.test(h)) return "neon (unclassified)";
  return "REMOTE (non-neon)";
}

if (!fs.existsSync(TEMP)) die("temp URL file not found");

// Read, then scrub the source file in place regardless of what happens next.
const raw = fs.readFileSync(TEMP, "utf8");
const url = raw.trim().replace(/^["']|["']$/g, "").replace(/^DATABASE_URL\s*=\s*/i, "").trim();

// Any exit path from here on must not leave the secret on disk.
process.on("exit", () => {
  try {
    if (fs.existsSync(TEMP)) {
      fs.writeFileSync(TEMP, crypto.randomBytes(512));
      fs.unlinkSync(TEMP);
    }
  } catch {
    /* best effort */
  }
});

if (!url) die("temp file is empty");
if (/\s/.test(url)) die("URL contains whitespace/newlines");
if (!/^postgres(ql)?:\/\//i.test(url)) die("not a postgres URL");

const kind = classify(url);
if (kind === "LOCAL") die("URL points at localhost — refusing to write it as the Neon target");
if (kind === "neon POOLED") die("host contains -pooler; the direct endpoint is required");
if (kind !== "neon direct") die(`host is ${kind}, expected a Neon direct endpoint`);

let parsed;
try {
  parsed = new URL(url);
} catch {
  die("URL does not parse");
}
if ((parsed.searchParams.get("sslmode") ?? "") !== "require") {
  die(`sslmode must be "require" (found "${parsed.searchParams.get("sslmode") ?? "none"}")`);
}
if (!parsed.username || !parsed.password) die("URL is missing credentials");

// Quote only when the value would otherwise be mangled by .env parsing.
function encodeForEnv(v) {
  const needsQuotes = /[\s#$`"']/.test(v);
  if (!needsQuotes) return v;
  if (v.includes('"')) die("value contains a double quote; cannot quote safely");
  return `"${v}"`;
}
const encoded = encodeForEnv(url);

for (const file of TARGETS) {
  if (!fs.existsSync(file)) die(`${file} does not exist`);

  const before = fs.readFileSync(file, "utf8");
  const eol = before.includes("\r\n") ? "\r\n" : "\n";
  const lines = before.split(/\r?\n/);

  let replaced = false;
  const out = lines.map((line) => {
    if (!replaced && /^\s*DATABASE_URL\s*=/.test(line)) {
      replaced = true;
      return `DATABASE_URL=${encoded}`;
    }
    return line;
  });
  if (!replaced) out.push(`DATABASE_URL=${encoded}`);

  // Preserve a trailing newline exactly as found.
  const trailing = before.endsWith("\n");
  let text = out.join(eol);
  if (trailing && !text.endsWith(eol)) text += eol;

  // Sanity: every non-DATABASE_URL key is untouched.
  const keysOf = (t) =>
    t
      .split(/\r?\n/)
      .map((l) => l.match(/^\s*([A-Z0-9_]+)\s*=/))
      .filter(Boolean)
      .map((m) => m[1])
      .join(",");
  if (keysOf(before) !== keysOf(text)) die(`key set changed in ${file} — aborting`);

  fs.writeFileSync(file, text);

  const st = fs.statSync(file);
  console.log(
    `${file}: host-type=${classify(url)} length=${url.length} quoted=${encoded !== url} ` +
      `mtime=${st.mtime.toISOString()} bytes=${st.size}`,
  );
}

console.log("temp file scrubbed and deleted");
