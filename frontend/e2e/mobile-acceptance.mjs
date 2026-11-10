// Mobile acceptance test: typing (fill) and sending with taps, on phone/tablet/desktop sizes, in Chromium and WebKit.
//   node e2e/mobile-acceptance.mjs <built site dir | https://url> <screenshot dir> [engines] [sizes]
// A site dir is served on http://127.0.0.1:${PORT:-3000} (add that origin to the backend's CORS_ORIGINS).
// Needs Playwright (npx playwright install chromium webkit; set NODE_PATH to where it is installed).
// The "keyboard" step shrinks the viewport to 55% height: an approximation, not a real on-screen keyboard.
import { createServer } from "node:http";
import { readFile, stat, mkdir, writeFile } from "node:fs/promises";
import { join, extname } from "node:path";
import { createRequire } from "node:module";
const require = createRequire(process.env.NODE_PATH ? process.env.NODE_PATH + "/x" : import.meta.url);
const pw = require("playwright");
const [site, out, engArg = "chromium,webkit", sizeArg] = process.argv.slice(2);
const SIZES = (sizeArg ?? "320x568,375x667,390x844,430x932,768x1024,1440x900,844x390").split(",").map(s => s.split("x").map(Number));
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".ico": "image/x-icon", ".txt": "text/plain" };
const PORT = Number(process.env.PORT ?? 3000);
const remote = /^https?:\/\//.test(site);
const BASE = remote ? site.replace(/\/$/, "") : `http://127.0.0.1:${PORT}`;
const srv = remote ? null : createServer(async (req, res) => {
  let p = decodeURIComponent(req.url.split("?")[0]); let f = join(site, p);
  try { if ((await stat(f)).isDirectory()) f = join(f, "index.html"); } catch { f = join(site, "404.html"); }
  try { res.writeHead(200, { "content-type": TYPES[extname(f)] ?? "application/octet-stream" }); res.end(await readFile(f)); }
  catch { res.writeHead(404); res.end("nf"); }
}).listen(PORT, "127.0.0.1");
await mkdir(out, { recursive: true });
const results = [];
const Q = [process.env.Q1 ?? "What floor plans do you have?", process.env.Q2 ?? "Can I tour on Saturday afternoon?"];
for (const eng of engArg.split(",")) {
  const browser = await pw[eng].launch();
  for (const [w, h] of SIZES) {
    const mobile = w < 900 && eng !== "firefox";
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile && eng === "chromium", hasTouch: mobile, deviceScaleFactor: 2 });
    const page = await ctx.newPage(); const errs = [];
    page.on("pageerror", e => errs.push(String(e))); page.on("console", m => m.type() === "error" && errs.push(m.text()));
    const tag = `${eng}-${w}x${h}`; const r = { tag, ok: true, notes: [] };
    const fail = (n) => { r.ok = false; r.notes.push("FAIL " + n); };
    try {
      await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
      const box = page.locator("textarea");
      await box.waitFor({ timeout: 15000 });
      if (await box.isDisabled()) fail("composer disabled (static replay, not live)");
      const ov = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (ov > 0) fail(`horizontal overflow ${ov}px`);
      await page.screenshot({ path: `${out}/${tag}-1-open.png` });
      const vis = async (loc) => { const b = await loc.boundingBox(); return b && b.y >= 0 && b.y + b.height <= (await page.evaluate(() => window.visualViewport?.height ?? innerHeight)) + 1; };
      if (!(await vis(box))) fail("composer not visible on open");
      if (!(await box.isDisabled()) && !(await vis(page.locator('a[href="tel:911"]').last()))) fail("911 link not visible on open");
      const sendBtn = page.locator('form button[type="submit"]');
      const tb = await sendBtn.boundingBox(); if (tb && (tb.width < 44 || tb.height < 44)) fail(`send target ${tb.width}x${tb.height}`);
      for (let i = 0; i < Q.length; i++) {
        const before = await page.locator('[role="article"]').count();
        if (mobile) await box.tap(); else await box.click();
        // keyboard approximation: the visual viewport shrinks by ~45% when a phone keyboard opens
        if (mobile && h > w) { await page.setViewportSize({ width: w, height: Math.round(h * 0.55) }); await page.waitForTimeout(250);
          if (!(await vis(box))) fail(`q${i + 1}: composer hidden with keyboard-height viewport`);
          const share = await page.evaluate(() => { const c = document.querySelector("textarea")?.closest(".sticky"); return c ? c.getBoundingClientRect().height / (window.visualViewport?.height ?? innerHeight) : 0; });
          r.notes.push(`q${i + 1}: composer uses ${Math.round(share * 100)}% of the keyboard-height screen`);
          if (share > 0.42) fail(`q${i + 1}: composer takes ${Math.round(share * 100)}% of the screen while typing`);
          if (!(await vis(page.locator('a[href="tel:911"]').last()))) fail(`q${i + 1}: 911 link not visible while typing`);
          await page.screenshot({ path: `${out}/${tag}-2-keyboard-q${i + 1}.png` }); }
        await box.fill(Q[i]);
        if (mobile) await sendBtn.tap(); else await sendBtn.click();
        await page.waitForFunction((n) => document.querySelectorAll('[role="article"]').length > n, before, { timeout: 20000 });
        await page.waitForTimeout(400);
        if (mobile && h > w) await page.setViewportSize({ width: w, height: h });
        await page.waitForTimeout(250);
        const last = page.locator('[role="article"]').last();
        const txt = (await last.innerText()).slice(0, 140).replace(/\s+/g, " ");
        r.notes.push(`q${i + 1} reply: ${txt}`);
        const lb = await last.boundingBox(); const cb = await box.boundingBox();
        if (lb && cb && lb.y > cb.y) fail(`q${i + 1}: newest reply starts below the composer`);
        const ov2 = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        if (ov2 > 0) fail(`q${i + 1}: horizontal overflow ${ov2}px`);
        await page.screenshot({ path: `${out}/${tag}-3-after-q${i + 1}.png` });
      }
      await page.reload({ waitUntil: "networkidle" }); await page.waitForTimeout(500);
      const kept = await page.locator('[role="article"]').count();
      r.notes.push(`after refresh: ${kept} assistant messages restored`);
      if (kept < Q.length + 1) fail(`refresh restored ${kept} assistant messages, expected ${Q.length + 1}`);
      await page.screenshot({ path: `${out}/${tag}-4-refresh.png` });
      // tap target audit (outside running text)
      const small = await page.evaluate(() => [...document.querySelectorAll("button, a, select, textarea, input")].filter(e => { const b = e.getBoundingClientRect(); return b.width && (b.height < 44 || b.width < 24) && !e.closest("p"); }).map(e => (e.textContent || e.tagName).trim().slice(0, 30) + ` ${Math.round(e.getBoundingClientRect().width)}x${Math.round(e.getBoundingClientRect().height)}`));
      if (small.length) r.notes.push("small targets: " + small.join("; "));
    } catch (e) { fail(String(e).split("\n")[0]); await page.screenshot({ path: `${out}/${tag}-x-error.png` }).catch(() => {}); }
    if (errs.length) r.notes.push("console: " + errs.slice(0, 3).join(" | ").slice(0, 300));
    results.push(r); console.log((r.ok ? "PASS " : "FAIL ") + tag + "\n   " + r.notes.join("\n   "));
    await ctx.close();
  }
  await browser.close();
}
await writeFile(`${out}/results.json`, JSON.stringify(results, null, 2));
srv?.close();
process.exitCode = results.every((r) => r.ok) ? 0 : 1;
