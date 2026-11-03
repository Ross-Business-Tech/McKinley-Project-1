#!/usr/bin/env node
// Builds a static export of the Next.js app and copies it to the repository's root `dist/`,
// which is what the team's here.now pipeline (scripts/, .github/workflows/herenow.yml) publishes.
// The static site has no server: it calls the FastAPI backend at NEXT_PUBLIC_API_BASE_URL.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(FRONTEND, "out");
const DIST = path.resolve(FRONTEND, "..", "dist");

fs.rmSync(OUT, { recursive: true, force: true });
execFileSync(process.execPath, [path.join(FRONTEND, "node_modules", "next", "dist", "bin", "next"), "build"], {
  cwd: FRONTEND,
  stdio: "inherit",
  env: { ...process.env, NEXT_STATIC_EXPORT: "1" },
});
fs.rmSync(DIST, { recursive: true, force: true });
fs.cpSync(OUT, DIST, { recursive: true });
console.log(`Static export copied to ${path.relative(process.cwd(), DIST) || "dist"}/`);
