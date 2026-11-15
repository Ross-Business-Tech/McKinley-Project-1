// Screen-records the app following script.json, paced to the narrator's voice.
// Usage: node demo-video/record.cjs <work_dir> <site_url>
// Writes <work_dir>/frames/*.jpg, frames.json (frame times) and timeline.json (when each line is spoken).
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const work = process.argv[2];
const site = (process.argv[3] || "http://localhost:4173").replace(/\/$/, "");
const script = JSON.parse(fs.readFileSync(path.join(__dirname, "script.json"), "utf8"));
const voice = JSON.parse(fs.readFileSync(path.join(work, "voice.json"), "utf8"));
const GAP = 0.28; // pause after each spoken line (seconds)
const LEAD = 0.2; // on-screen action starts this long after the line starts

const sleep = (s) => new Promise((r) => setTimeout(r, s * 1000));
const now = () => Date.now() / 1000;

// A visible mouse pointer (headless browsers don't draw one).
const CURSOR = () => {
  const add = () => {
    if (document.getElementById("__demo_cursor")) return;
    const c = document.createElement("div");
    c.id = "__demo_cursor";
    c.innerHTML =
      '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l15 10.5-6.6 1.2 4 7.6-3 1.6-4-7.7L4 20z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>' +
      '<span id="__demo_ring"></span>';
    const x = window.__cx ?? innerWidth * 0.55, y = window.__cy ?? innerHeight * 0.6;
    c.style.cssText = `position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;transform:translate(${x}px,${y}px);transition:transform .7s cubic-bezier(.4,0,.2,1);filter:drop-shadow(0 1px 2px rgba(0,0,0,.35))`;
    const st = document.createElement("style");
    st.textContent = `#__demo_ring{position:absolute;left:-14px;top:-14px;width:30px;height:30px;border-radius:50%;border:3px solid rgba(30,90,70,.85);opacity:0;transform:scale(.3)}
      #__demo_ring.go{animation:__demo_ring .45s ease-out}
      @keyframes __demo_ring{0%{opacity:1;transform:scale(.3)}100%{opacity:0;transform:scale(1.4)}}`;
    document.documentElement.appendChild(st);
    document.documentElement.appendChild(c);
    const b = document.createElement("div");
    b.id = "__demo_badge";
    b.style.cssText = "position:fixed;left:24px;bottom:22px;z-index:2147483646;pointer-events:none;background:#2c4a6b;color:#fff;font:600 15px/1 Inter,system-ui,sans-serif;letter-spacing:.01em;padding:11px 16px;border-radius:999px;box-shadow:0 2px 10px rgba(0,0,0,.18);display:none";
    const label = sessionStorage.getItem("__demo_badge");
    if (label) { b.textContent = label; b.style.display = "block"; }
    document.documentElement.appendChild(b);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", add);
  else add();
};

const esc = (t) => String(t).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch]);
const coverHtml = (c) => `<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;height:100%;font-family:Inter,system-ui,sans-serif}
  body{background:linear-gradient(135deg,#2c4a6b 0%,#4e6f92 62%,#6f8fb0 100%);color:#fff;display:flex;align-items:center}
  .wrap{padding:0 96px;width:100%;box-sizing:border-box}
  .brand{font-weight:700;font-size:30px;letter-spacing:-.01em;opacity:.95}
  .kicker{margin-top:70px;display:inline-block;font-weight:600;font-size:16px;letter-spacing:.14em;text-transform:uppercase;background:rgba(255,255,255,.16);padding:9px 14px;border-radius:6px}
  h1{margin:48px 0 0;font-size:84px;line-height:1.04;letter-spacing:-.02em;font-weight:700}
  .sub{margin-top:20px;font-size:26px;line-height:1.35;max-width:820px;opacity:.92}
  ol{margin:48px 0 0;padding:0;list-style:none;display:flex;gap:12px;flex-wrap:wrap}
  li{font-size:17px;font-weight:500;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.28);padding:9px 14px;border-radius:999px}
  li b{opacity:.7;margin-right:6px}
  .foot{margin-top:40px;font-size:16px;opacity:.8}
</style></head><body><div class="wrap">
  <div class="brand">McKinley</div>
  ${c.kicker ? `<div class="kicker">${esc(c.kicker)}</div>` : ""}
  <h1>${esc(c.title || "")}</h1>
  <div class="sub">${esc(c.subtitle || "")}</div>
  ${(c.chapters || []).length ? `<ol>${c.chapters.map((t, i) => `<li><b>${i + 1}</b>${esc(t)}</li>`).join("")}</ol>` : ""}
  <div class="foot">${esc(c.footer || "")}</div>
</div></body></html>`;

(async () => {
  const exe = fs.existsSync("/opt/pw-browsers/chromium") ? "/opt/pw-browsers/chromium" : undefined;
  const browser = await chromium.launch({ executablePath: exe });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  await page.goto(site + "/");
  await page.waitForLoadState("networkidle");
  if (script.scenes[0]?.cover) {
    await page.setContent(coverHtml(script.cover || {}));
    await page.evaluate(() => { const c = document.getElementById("__demo_cursor"); if (c) c.style.display = "none"; });
    if (process.env.COVER_PNG) await page.screenshot({ path: process.env.COVER_PNG });
  }
  await sleep(1);

  // Capture frames with the browser's screencast (sharper than the built-in video recorder).
  const framesDir = path.join(work, "frames");
  fs.rmSync(framesDir, { recursive: true, force: true });
  fs.mkdirSync(framesDir, { recursive: true });
  const frames = [];
  const cdp = await ctx.newCDPSession(page);
  cdp.on("Page.screencastFrame", async (f) => {
    const file = path.join(framesDir, `${String(frames.length).padStart(6, "0")}.jpg`);
    frames.push({ file, t: f.metadata.timestamp });
    fs.writeFileSync(file, Buffer.from(f.data, "base64"));
    cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
  // Keep the screen "alive" so frame times stay accurate even when nothing moves.
  const nudge = setInterval(() => page.evaluate(() => { document.documentElement.style.outlineColor = `rgba(0,0,0,0.00${Date.now() % 9})`; }).catch(() => {}), 200);

  const moveTo = async (loc) => {
    await loc.scrollIntoViewIfNeeded().catch(() => {});
    const box = await loc.boundingBox();
    if (!box) return;
    const x = box.x + Math.min(box.width / 2, 60), y = box.y + box.height / 2;
    await page.evaluate(([x, y]) => {
      window.__cx = x; window.__cy = y;
      const c = document.getElementById("__demo_cursor");
      if (c) c.style.transform = `translate(${x}px,${y}px)`;
    }, [x, y]);
    await sleep(0.8);
  };
  const ring = () => page.evaluate(() => {
    const r = document.getElementById("__demo_ring");
    if (r) { r.classList.remove("go"); void r.offsetWidth; r.classList.add("go"); }
  });
  const find = async (text) => {
    const re = new RegExp(text, "i");
    const cands = [
      page.getByRole("button", { name: re }),
      page.getByRole("tab", { name: re }),
      page.getByRole("link", { name: re }),
      page.getByText(re),
    ];
    for (const c of cands) {
      const v = c.filter({ visible: true });
      if (await v.count()) return v.last();
    }
    throw new Error(`Could not find "${text}" on screen`);
  };

  let onCover = !!script.scenes[0]?.cover, chapter = "";
  const setBadge = (label) => page.evaluate((label) => {
    sessionStorage.setItem("__demo_badge", label || "");
    const b = document.getElementById("__demo_badge");
    if (b) { b.textContent = label || ""; b.style.display = label ? "block" : "none"; }
  }, label).catch(() => {});
  const run = async (a) => {
    if (a.type) {
      const box = page.locator("textarea:visible").first();
      await moveTo(box);
      await ring();
      await box.click();
      await page.keyboard.type(a.type, { delay: 24 });
      await sleep(0.3);
    } else if (a.press) {
      await page.keyboard.press(a.press);
      await sleep(1.2);
    } else if (a.goto !== undefined) {
      if (onCover || new URL(page.url()).pathname !== a.goto) {
        await page.goto(site + a.goto);
        await page.waitForLoadState("networkidle").catch(() => {});
        onCover = false;
        await setBadge(chapter);
        await sleep(0.6);
      }
    } else if (a.click) {
      const el = await find(a.click);
      await moveTo(el);
      await ring();
      await el.click();
      await sleep(0.9);
    } else if (a.hover) {
      await moveTo(await find(a.hover));
    } else if (a.select !== undefined) {
      const sel = page.locator("select:visible").first();
      await moveTo(sel);
      await ring();
      await sel.selectOption(a.select);
      await sleep(0.9);
    } else if (a.scroll) {
      await page.mouse.move(640, 400);
      const steps = 12;
      for (let i = 0; i < steps; i++) { await page.mouse.wheel(0, a.scroll / steps); await sleep(0.03); }
      await sleep(0.4);
    } else if (a.wait) {
      await sleep(a.wait);
    }
  };

  const timeline = { lines: [], scenes: [] };
  let vi = 0;
  for (const [si, scene] of script.scenes.entries()) {
    const sceneStart = now();
    chapter = scene.cover ? "" : scene.chapter || "";
    if (!scene.cover && !onCover) await setBadge(chapter);
    for (const step of scene.steps) {
      const v = voice[vi++];
      const t0 = now();
      timeline.lines.push({ scene: si, short: step.short ?? !!scene.short, t: t0, wav: v.wav, duration: v.duration, text: step.caption || step.say });
      await sleep(LEAD);
      for (const a of step.do || []) {
        try { await run(a); } catch (e) { console.error(`  ! scene "${scene.id}": ${e.message}`); }
      }
      const left = t0 + v.duration + GAP - now();
      if (left > 0) await sleep(left);
    }
    if (si < script.scenes.length - 1) await sleep(0.6); // a short breath between chapters
    timeline.scenes.push({ id: scene.id, short: !!scene.short, start: sceneStart, end: now() });
    console.log(`  recorded scene ${scene.id} (${(now() - sceneStart).toFixed(1)}s)`);
  }
  await sleep(1.2);
  timeline.end = now();
  clearInterval(nudge);
  await cdp.send("Page.stopScreencast");
  await sleep(0.3);
  await browser.close();
  fs.writeFileSync(path.join(work, "frames.json"), JSON.stringify(frames));
  fs.writeFileSync(path.join(work, "timeline.json"), JSON.stringify(timeline, null, 1));
  console.log(`Recorded ${frames.length} frames, ${(timeline.end - frames[0].t).toFixed(1)}s`);
})();
