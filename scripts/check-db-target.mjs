import fs from "node:fs";
import path from "node:path";

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

function inspect(file) {
  if (!fs.existsSync(file)) {
    console.log(`\n${file}: DOES NOT EXIST`);
    return;
  }
  const st = fs.statSync(file);
  const raw = fs.readFileSync(file, "utf8");
  console.log(`\n${file}`);
  console.log(`  modified: ${st.mtime.toISOString()}`);
  console.log(`  bytes: ${st.size}  has-BOM: ${raw.charCodeAt(0) === 0xfeff}`);

  const lines = raw.split(/\r?\n/);
  const hits = [];
  lines.forEach((line, i) => {
    if (/DATABASE_URL/.test(line)) hits.push({ i: i + 1, line });
  });
  console.log(`  lines mentioning DATABASE_URL: ${hits.length}`);
  for (const { i, line } of hits) {
    const commented = /^\s*#/.test(line);
    const m = line.match(/^\s*#?\s*DATABASE_URL\s*=\s*(.*)$/);
    let verdict = "no value";
    let valueLen = 0;
    if (m) {
      const v = m[1].trim().replace(/^["']|["']$/g, "");
      valueLen = v.length;
      verdict = v ? classify(v) : "EMPTY";
    }
    console.log(`    line ${i}: commented=${commented} value-length=${valueLen} -> ${verdict}`);
  }
}

for (const f of [".env", "apps/api/.env", "apps/web/.env", "packages/shared/.env"]) inspect(f);

// Any other env files anywhere in the repo (excluding node_modules)?
function walk(dir, out = [], depth = 0) {
  if (depth > 3) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name === ".git") continue;
    const full = path.join(dir, e.name);
    if (e.isDirectory()) walk(full, out, depth + 1);
    else if (/^\.env/.test(e.name)) out.push(full);
  }
  return out;
}
console.log("\nenv files found in repo:");
for (const f of walk(".")) console.log(`  ${f}`);
