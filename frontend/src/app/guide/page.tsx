import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";

// Maintainer guide (draft v0.1). A static page: everything here is plain text and screenshots, no backend calls.
// Screenshots live in public/guide/ and were taken from the static preview build at phone (390 px) and desktop size.

export const metadata: Metadata = {
  title: "Maintainer guide (draft) | McKinley Help (prototype)",
  description: "How to look after the McKinley assistant: how it works, how to change it, fix it and add to it.",
};

const REPO = "https://github.com/Ross-Business-Tech/McKinley-Project-1/blob/development/";

const SECTIONS = [
  { id: "start", title: "1. What you are maintaining" },
  { id: "tour", title: "2. Guided tour, with screenshots" },
  { id: "how", title: "3. How one message is handled" },
  { id: "change", title: "4. Changing something" },
  { id: "fix", title: "5. Fixing a problem" },
  { id: "add", title: "6. Adding a new function" },
  { id: "check", title: "7. Before you share a change" },
  { id: "limits", title: "8. Known limits" },
  { id: "next", title: "9. Still to write" },
];

function Code({ children }: { children: ReactNode }) {
  return <code className="rounded bg-mk-brand-soft px-1.5 py-0.5 font-mono text-[0.85em] break-words text-mk-brand-strong">{children}</code>;
}

function FileLink({ path }: { path: string }) {
  return (
    <a href={REPO + path} className="mk-focus font-mono text-[0.85em] break-all text-mk-brand-hover underline underline-offset-2">
      {path}
    </a>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-6 border-t border-mk-line pt-8">
      <h2 className="font-heading text-2xl font-semibold text-mk-ink">{title}</h2>
      <div className="mt-4 space-y-4 leading-relaxed">{children}</div>
    </section>
  );
}

function Step({ n, title, img, alt, wide, children }: { n: number; title: string; img: string; alt: string; wide?: boolean; children: ReactNode }) {
  return (
    <figure className={`grid gap-4 rounded-xl border border-mk-line bg-mk-surface p-4 sm:p-6 ${wide ? "" : "md:grid-cols-[minmax(0,1fr)_260px]"}`}>
      <figcaption className="space-y-3">
        <p className="font-heading text-lg font-semibold">
          <span className="mr-2 inline-flex size-7 items-center justify-center rounded-full bg-mk-brand text-sm text-white">{n}</span>
          {title}
        </p>
        <div className="space-y-3 text-[0.95rem] leading-relaxed">{children}</div>
      </figcaption>
      <Image
        src={img}
        alt={alt}
        width={wide ? 1440 : 780}
        height={wide ? 900 : 1688}
        className={`h-auto w-full rounded-lg border border-mk-line ${wide ? "" : "mx-auto max-w-[260px]"}`}
      />
    </figure>
  );
}

function Recipe({ title, where, children, warn }: { title: string; where: string[]; children: ReactNode; warn?: string }) {
  return (
    <div className="rounded-xl border border-mk-line bg-mk-surface p-4 sm:p-5">
      <h3 className="font-heading text-lg font-semibold">{title}</h3>
      <div className="mt-2 space-y-2 text-[0.95rem] leading-relaxed">{children}</div>
      <p className="mt-3 text-sm text-mk-muted">Where:</p>
      <ul className="mt-1 space-y-1">
        {where.map((w) => (
          <li key={w}>
            <FileLink path={w} />
          </li>
        ))}
      </ul>
      {warn && <p className="mt-3 rounded-md bg-mk-attention-soft p-3 text-sm text-mk-attention">{warn}</p>}
    </div>
  );
}

const PIPELINE: [string, string, string][] = [
  ["Receive", "The message arrives with the conversation so far.", "backend/app/chat_engine.py"],
  ["Who is this?", "Resident, prospect, vendor or unknown visitor (demo sign-in for now).", "backend/app/auth.py"],
  ["Safety first", "Fire, gas, medical, threats, self-harm: fixed, approved 911 / 988 guidance before anything else.", "backend/app/risk/"],
  ["Privacy filter", "Only an allowed, trimmed summary of the account is ever passed on. No phone numbers, rent or staff notes.", "backend/app/context.py"],
  ["Decide", "The decision gate picks the workflow (repair, tour, status, FAQ, talk to a person) and how urgent it is.", "backend/app/gates/"],
  ["Plan", "Asks the next question, or builds a read-back card for the person to check.", "backend/app/actions.py"],
  ["Write the reply", "Approved wording; the AI model is only used when needed (often skipped).", "backend/app/templates.py"],
  ["Check the reply", "Nine automatic checks: no promises we can't keep, no private data, right language…", "backend/app/chat_engine.py"],
  ["Hand off", "Marks when a person should help, and which team.", "backend/app/handoff.py"],
  ["Save", "Only after the person presses Send. Saved to the prototype store (DEMO-…).", "backend/app/db.py"],
];

const TROUBLE: [string, string, string][] = [
  [
    "The chat says the assistant can't be reached",
    "The backend isn't running, or the website's address isn't on its allowed list.",
    "Start it with npm run backend:dev. Add the website address to CORS_ORIGINS in backend/.env.",
  ],
  [
    "Replies say NEEDS_API_KEY",
    "An AI provider is chosen but its key is missing.",
    "Add the key to backend/.env (never to the code), or set LLM_PROVIDER=mock to use fixed replies.",
  ],
  [
    "Replies fail with MODEL_SWITCHED",
    "The provider answered with a different model than the one configured. This is refused on purpose.",
    "Check LLM_MODEL / GEMINI_MODEL, then run the preflight check (see section 4).",
  ],
  [
    "A resident sign-in finds no record",
    "The made-up resident spreadsheet isn't on this computer (it is kept out of GitHub).",
    "Ask the project owner for the sample workbook and put it in backend/data/.",
  ],
  [
    "An emergency message got no safety alert",
    "The safety rules missed a wording. This is the most serious kind of bug.",
    "Find it in the staff inspector, add the wording as a test, extend the rules in backend/app/risk/, and have someone else review it.",
  ],
  [
    "The test link shows old conversations",
    "The preview link replays recorded conversations, it does not run the assistant live.",
    "Re-record them: cd backend && uv run python -m app.export_demo, then publish again.",
  ],
  [
    "Staff tabs say they need a backend",
    "Expected on the test link: only the Conversation inspector works without a backend.",
    "Run the app locally to use the other tabs.",
  ],
];

const ADD_STEPS: [string, ReactNode][] = [
  ["Write down the job", <>One sentence on what the person wants and what the assistant should save. Check the workflow list in <FileLink path="docs/workflows/traceability.md" />.</>],
  ["Teach it to recognise the request", <>Add words and phrases to the detectors in <FileLink path="backend/app/intake.py" />, with examples that should and should not match.</>],
  ["Decide where it goes in the plan", <>The planner in <FileLink path="backend/app/actions.py" /> is an ordered list of checks, and the order matters. Add the new check in the right place; never reorder existing ones.</>],
  ["Write the words", <>Customer replies go in <FileLink path="backend/app/templates.py" /> (English and Spanish). On-screen labels go in <FileLink path="frontend/src/lib/customer.ts" />.</>],
  ["Show it on screen", <>If it saves something, add a read-back card in <FileLink path="frontend/src/components/customer/ActionCard.tsx" /> and keep <FileLink path="frontend/src/lib/types.ts" /> in step with the backend.</>],
  ["Test it", <>Add backend tests in <Code>backend/tests/</Code> that pin the new behaviour, then run the full checks in section 7.</>],
  ["Update the docs and share", <>Update the workflow list and README status, then open a pull request into <Code>development</Code>.</>],
];

export default function GuidePage() {
  return (
    <div className="flex min-h-full flex-col">
      <header className="mk-band bg-mk-brand text-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <p className="flex flex-wrap items-baseline gap-x-3">
            <span className="font-heading text-xl font-bold">McKinley</span>
            <span className="font-heading text-base font-medium">Maintainer guide</span>
          </p>
          <nav className="flex gap-2 text-sm">
            <Link href="/" prefetch={false} className="mk-focus inline-flex min-h-11 items-center rounded-md border border-white/80 px-3 font-medium hover:bg-white/10">
              Chat
            </Link>
            <Link href="/staff/" prefetch={false} className="mk-focus inline-flex min-h-11 items-center rounded-md border border-white/80 px-3 font-medium hover:bg-white/10">
              Staff console
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-6">
        <p className="inline-flex rounded-full bg-mk-attention-soft px-3 py-1 text-sm font-medium text-mk-attention">Draft v0.1 · November 2026</p>
        <h1 className="mt-3 font-heading text-3xl font-bold sm:text-4xl">How to look after the McKinley assistant</h1>
        <p className="mt-3 max-w-3xl text-lg leading-relaxed text-mk-muted">
          For whoever maintains the chatbot after us: how it works, where to change things, how to fix common problems
          and how to add a new function. The chatbot is not final yet, so this is an early outline: screenshots and
          details will change.
        </p>

        <nav aria-label="Contents" className="mt-6 rounded-xl border border-mk-line bg-mk-surface p-4 sm:p-5">
          <p className="font-heading font-semibold">Contents</p>
          <ol className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="mk-focus inline-flex min-h-9 items-center text-mk-brand-hover underline-offset-2 hover:underline">
                  {s.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="mt-10 space-y-12">
          <Section id="start" title={SECTIONS[0].title}>
            <p>The assistant has two parts that work together:</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-mk-line bg-mk-surface p-4">
                <p className="font-heading font-semibold">The chat (what customers see)</p>
                <p className="mt-1 text-[0.95rem]">Residents report repairs, check on requests and ask questions. People looking for a home ask about communities and request tours. Lives in <Code>frontend/</Code>.</p>
              </div>
              <div className="rounded-xl border border-mk-line bg-mk-surface p-4">
                <p className="font-heading font-semibold">The brain (what decides the reply)</p>
                <p className="mt-1 text-[0.95rem]">Checks safety, decides what the person needs, writes the reply and saves requests. Lives in <Code>backend/</Code>.</p>
              </div>
            </div>
            <p>
              There is also a <Link href="/staff/" className="mk-focus text-mk-brand-hover underline underline-offset-2">staff console</Link> that shows
              what the assistant decided behind every reply. It is your main tool when something looks wrong.
            </p>
            <p className="rounded-md bg-mk-brand-soft p-3 text-[0.95rem]">
              <strong>Golden rules:</strong> made-up data only, never put a password or API key in the code, and never
              change the safety wording without a second person reviewing it.
            </p>
          </Section>

          <Section id="tour" title={SECTIONS[1].title}>
            <p>Open the <Link href="/" className="mk-focus text-mk-brand-hover underline underline-offset-2">chat</Link> and follow along. On the test link typing is off: tap the suggestions instead.</p>
            <div className="space-y-6">
              <Step n={1} title="The chat opens" img="/guide/chat-start.jpg" alt="Phone screenshot of the chat's opening screen with suggested questions">
                <p>The assistant says it is automated and offers a person at any time. The <strong>Demo sign-in</strong> menu at the top lets you act as a made-up resident or prospect.</p>
                <p>Change the greeting or suggestions in <FileLink path="frontend/src/lib/customer.ts" />.</p>
              </Step>
              <Step n={2} title="A repair request is read back" img="/guide/repair-readback.jpg" alt="Phone screenshot of a repair request card waiting to be sent">
                <p>After a few questions the assistant shows a card with everything it understood. Each line says where it came from: <em>you told us</em>, <em>on your account</em> or <em>added by the assistant</em>.</p>
                <p>Nothing is saved until the person presses Send. Keep it that way when you change a workflow.</p>
              </Step>
              <Step n={3} title="The request is saved" img="/guide/repair-saved.jpg" alt="Phone screenshot of a saved repair request with a DEMO reference number">
                <p>The person gets a reference number (<Code>DEMO-WO-…</Code>) and can ask for its status later.</p>
                <p>Today it is only saved inside the prototype. Connecting it to McKinley&apos;s real work-order system is future work.</p>
              </Step>
              <Step n={4} title="An emergency always comes first" img="/guide/safety-alert.jpg" alt="Phone screenshot of a red gas-leak safety alert telling the person to leave and call 911">
                <p>Words like gas, fire or &quot;not breathing&quot; trigger fixed, approved guidance before anything else. The AI model never writes this text.</p>
                <p>This is the most sensitive part of the app: see the warning in section 4.</p>
              </Step>
              <Step n={5} wide title="See why it replied that way" img="/guide/staff-inspector.jpg" alt="Desktop screenshot of the staff console's conversation inspector showing the decision behind a reply">
                <p>
                  In the <Link href="/staff/" className="mk-focus text-mk-brand-hover underline underline-offset-2">staff console</Link>, the
                  <strong> Conversation inspector</strong> shows each message, the workflow chosen, the urgency, which account facts were used, whether a person should help, and whether the reply passed its checks.
                </p>
                <p>When someone reports a strange reply, start here.</p>
              </Step>
            </div>
          </Section>

          <Section id="how" title={SECTIONS[2].title}>
            <p>Every message goes through the same ten steps, in this order. If you know which step went wrong, you know which file to open.</p>
            <ol className="space-y-2">
              {PIPELINE.map(([name, what, where], i) => (
                <li key={name} className={`grid gap-1 rounded-lg border p-3 sm:grid-cols-[180px_minmax(0,1fr)] sm:gap-4 ${i === 2 ? "border-mk-danger/40 bg-mk-danger-soft" : "border-mk-line bg-mk-surface"}`}>
                  <p className="font-heading font-semibold">
                    {i + 1}. {name}
                  </p>
                  <div className="text-[0.95rem]">
                    <p>{what}</p>
                    <p className="mt-1">
                      <FileLink path={where} />
                    </p>
                  </div>
                </li>
              ))}
            </ol>
            <p className="text-sm text-mk-muted">
              Technical detail: <FileLink path="docs/architecture/overview.md" /> and the diagrams in <FileLink path="docs/diagrams/" />.
            </p>
          </Section>

          <Section id="change" title={SECTIONS[3].title}>
            <p>The most common changes, and where to make them.</p>
            <div className="grid gap-4 md:grid-cols-2">
              <Recipe title="Change an FAQ answer" where={["backend/app/content/knowledge_base.json"]}>
                <p>Each topic has keywords, an English and Spanish answer and a status. Only topics marked <Code>approved</Code> are shown to customers; the rest say the team will follow up.</p>
              </Recipe>
              <Recipe title="Change what the assistant says" where={["backend/app/templates.py", "frontend/src/lib/customer.ts"]}>
                <p>Replies are in <Code>templates.py</Code> (English and Spanish side by side). Buttons, labels and the greeting are in <Code>customer.ts</Code>. Add a new entry rather than cutting an existing sentence in half.</p>
              </Recipe>
              <Recipe
                title="Change the emergency wording"
                where={["backend/app/risk/responses.py", "backend/app/risk/policy.py"]}
                warn="Safety-critical. Needs tests, an independent reviewer, and McKinley's approval before real use."
              >
                <p>The fixed safety messages and the rules for when each one shows.</p>
              </Recipe>
              <Recipe title="Switch or connect the AI model" where={["backend/.env.example"]}>
                <p>Copy it to <Code>backend/.env</Code> and set <Code>LLM_PROVIDER</Code> (gemini, openrouter or mock) and the matching key. That file is never committed. Check the setup without using any credit: <Code>uv run python -m app.live_eval.preflight</Code>.</p>
              </Recipe>
              <Recipe title="Change colours and look" where={["frontend/src/app/globals.css", "docs/design/BRAND_SYSTEM.md"]}>
                <p>All colours are named tokens (<Code>mk-brand</Code>, <Code>mk-danger</Code>…). Green means saved, amber means a person should help, red means emergency; keep those meanings.</p>
              </Recipe>
              <Recipe title="Refresh the test-link demo" where={["backend/app/export_demo.py", "frontend/public/demo/snapshot.json"]}>
                <p>After changing replies, re-record the conversations the test link replays: <Code>cd backend && uv run python -m app.export_demo</Code>.</p>
              </Recipe>
            </div>
          </Section>

          <Section id="fix" title={SECTIONS[4].title}>
            <p>What you see, the usual cause, and what to do.</p>
            <div className="space-y-3">
              {TROUBLE.map(([seen, why, todo]) => (
                <div key={seen} className="rounded-xl border border-mk-line bg-mk-surface p-4">
                  <p className="font-heading font-semibold">{seen}</p>
                  <dl className="mt-2 grid gap-1 text-[0.95rem] sm:grid-cols-[110px_minmax(0,1fr)]">
                    <dt className="text-mk-muted">Likely cause</dt>
                    <dd>{why}</dd>
                    <dt className="text-mk-muted">What to do</dt>
                    <dd>{todo}</dd>
                  </dl>
                </div>
              ))}
            </div>
            <p className="text-sm text-mk-muted">Can&apos;t find it here? Check <FileLink path="docs/PROJECT_HANDOFF.md" /> for open issues.</p>
          </Section>

          <Section id="add" title={SECTIONS[5].title}>
            <p>For example, letting residents book an amenity or ask about parking. Work through these steps in order:</p>
            <ol className="space-y-3">
              {ADD_STEPS.map(([title, body], i) => (
                <li key={title} className="flex gap-3">
                  <span className="mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-mk-brand text-sm font-semibold text-white">{i + 1}</span>
                  <div>
                    <p className="font-heading font-semibold">{title}</p>
                    <p className="text-[0.95rem]">{body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Section>

          <Section id="check" title={SECTIONS[6].title}>
            <p>Run these from the project folder. Everything must pass before a pull request.</p>
            <pre className="overflow-x-auto rounded-xl bg-mk-ink p-4 font-mono text-sm leading-relaxed text-white">
              {`cd backend && uv run pytest && uv run ruff check .
cd .. && npm run lint && npm run typecheck && npm test
npm run build && npm run smoke
npm run publish:preview`}
            </pre>
            <ul className="list-disc space-y-1 pl-5">
              <li>Look at the phone screenshots the smoke test saves; most people use a phone.</li>
              <li>Open a pull request into <Code>development</Code> with the test link. Never push to <Code>main</Code>.</li>
              <li>Update any document your change makes untrue.</li>
            </ul>
          </Section>

          <Section id="limits" title={SECTIONS[7].title}>
            <p className="rounded-md bg-mk-danger-soft p-3 font-medium text-mk-danger">This is a prototype. It is not ready for real customers.</p>
            <ul className="list-disc space-y-2 pl-5">
              <li><strong>Missed emergencies:</strong> the safety rules still miss some urgent messages in testing. This blocks release.</li>
              <li><strong>No real sign-in:</strong> the demo sign-in is chosen in the browser.</li>
              <li><strong>Nothing is connected:</strong> no work-order system, no texts or emails, nobody is paged.</li>
              <li><strong>Mostly tested with fixed replies:</strong> the real AI model has barely been tested.</li>
            </ul>
            <p className="text-sm text-mk-muted">Full list: <FileLink path="docs/PROJECT_HANDOFF.md" />.</p>
          </Section>

          <Section id="next" title={SECTIONS[8].title}>
            <p>Planned for the final version of this guide, once the chatbot is settled:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Fresh screenshots of the final chat and console</li>
              <li>A short screen-recording walkthrough</li>
              <li>Who owns what, and who to contact at McKinley</li>
              <li>How to deploy and update the live site</li>
              <li>A checklist for approving new FAQ answers and safety wording</li>
            </ul>
          </Section>
        </div>
      </main>

      <footer className="border-t border-mk-line px-4 py-6 text-center text-sm text-mk-muted">Prototype with made-up data. Emergency? Call 911.</footer>
    </div>
  );
}
