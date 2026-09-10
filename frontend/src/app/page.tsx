import Link from "next/link";
import type { CSSProperties } from "react";

const section: CSSProperties = { padding: "48px 0" };
const h2: CSSProperties = { margin: "0 0 12px", fontSize: 20 };
const prose: CSSProperties = { color: "var(--ink-muted)", maxWidth: "65ch" };
const card: CSSProperties = {
  background: "var(--card)",
  borderRadius: 12,
  padding: 20,
};
const btn: CSSProperties = {
  display: "inline-block",
  padding: "12px 16px",
  minHeight: 44,
  fontSize: 15,
  fontWeight: 700,
  borderRadius: 8,
  color: "#fff",
  textDecoration: "none",
};
const btnGhost: CSSProperties = {
  ...btn,
  background: "var(--card)",
  color: "var(--ink)",
  border: "1px solid var(--border)",
};
const num: CSSProperties = { fontVariantNumeric: "tabular-nums" };

function Bar({ label, ms, pct, accent }: { label: string; ms: number; pct: number; accent?: boolean }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <strong>{label}</strong>
        <span style={num}>{ms.toLocaleString()} ms</span>
      </div>
      <div
        role="img"
        aria-label={`${label}: ${ms.toLocaleString()} milliseconds`}
        style={{ background: "var(--surface)", borderRadius: 8, height: 16 }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: 16,
            borderRadius: 8,
            background: accent ? "var(--accent)" : "var(--ink)",
          }}
        />
      </div>
    </div>
  );
}

export default function Landing() {
  return (
    <main style={{ maxWidth: 1000, margin: "0 auto", padding: 24 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0" }}>
        <strong style={{ fontSize: 18 }}>LinguaSwitch</strong>
        <nav style={{ display: "flex", gap: 12 }}>
          <Link href="/demo" style={{ ...btn, background: "var(--accent)" }}>
            Live demo
          </Link>
          <a href="https://github.com/Siddesh-bype/LinguaSwitch" style={btnGhost}>
            GitHub
          </a>
        </nav>
      </header>

      <section style={section}>
        <h1 style={{ margin: "0 0 8px", fontSize: 28, maxWidth: "22ch" }}>
          Does native code-switching beat segment-and-route for Hinglish voice?
        </h1>
        <p style={prose}>
          Indians talk to voice assistants in Hinglish — Hindi and English inside one sentence.
          LinguaSwitch tests two ways to speak it: one native code-switched call against the
          stitch-together baseline, on the same 10 sentences, with blind human ratings and
          measured latency.
        </p>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 16 }}>
          <Link href="/demo" style={{ ...btn, background: "var(--accent)" }}>
            Try the live demo
          </Link>
          <a
            href="https://github.com/Siddesh-bype/LinguaSwitch/blob/main/RIME_EVIDENCE.md"
            style={btnGhost}
          >
            Read the evidence
          </a>
        </div>
      </section>

      <section style={section}>
        <h2 style={h2}>Measured so far</h2>
        <div style={{ ...card, display: "flex", gap: 24, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 28, fontWeight: 700, ...num }}>2.3×</div>
            <p style={prose}>faster end-to-end, native vs baseline (mean total)</p>
          </div>
          <div>
            <div style={{ fontSize: 28, fontWeight: 700, ...num }}>10/10</div>
            <p style={prose}>sentences where native was faster (latency half)</p>
          </div>
          <div>
            <div style={{ fontSize: 28, fontWeight: 700, ...num }}>1 vs 3.3</div>
            <p style={prose}>API calls per sentence, native vs baseline average</p>
          </div>
        </div>
      </section>

      <section style={section}>
        <h2 style={h2}>Why the baseline loses</h2>
        <div style={{ ...card, marginBottom: 16 }}>
          <h3 style={{ margin: "0 0 8px", fontSize: 18 }}>The problem</h3>
          <p style={prose}>
            Mid-sentence language switches break naive TTS pipelines: detect the language per
            chunk, swap the whole voice config, concatenate the audio. Every boundary is a
            potential seam — and a Rime voice serves exactly one language, so the voice swap
            is structural, not a bug you can configure away.
          </p>
        </div>
        <div style={card}>
          <h3 style={{ margin: "0 0 8px", fontSize: 18 }}>The alternative</h3>
          <p style={prose}>
            One Rime Coda call with the mixed-language text. The model code-switches internally:
            no router, no per-chunk calls, no concatenation. This page exists to test whether
            that actually sounds better — not to assume it.
          </p>
        </div>
      </section>

      <section style={section}>
        <h2 style={h2}>Latency: native vs baseline (mean of 10 sentences)</h2>
        <div style={card}>
          <Bar label="Path A total" ms={2449} pct={44} accent />
          <Bar label="Path B total" ms={5523} pct={100} />
          <Bar label="Path A time-to-first-audio" ms={1234} pct={22} accent />
          <Bar label="Path B time-to-first-audio" ms={2521} pct={46} />
          <p style={{ ...prose, margin: "12px 0 0" }}>
            Full per-sentence table in RIME_EVIDENCE.md. Baseline cost = Groq segmentation
            (~1.3 s mean) + one Rime call per language run, sequential.
          </p>
        </div>
      </section>

      <section style={section}>
        <h2 style={h2}>The demo</h2>
        <p style={prose}>
          Pick a sentence or type your own Hinglish, generate each path, play both side by
          side. Segment tags show exactly how the router split the text and which voice
          spoke each run.
        </p>
        <img
          src="/shots/ui-results.png"
          alt="LinguaSwitch demo showing Path A and Path B results with latency numbers and language segment tags"
          loading="lazy"
          style={{ width: "100%", borderRadius: 12, border: "1px solid var(--border)", marginTop: 16 }}
        />
        <div style={{ marginTop: 16 }}>
          <Link href="/demo" style={{ ...btn, background: "var(--accent)" }}>
            Open the demo
          </Link>
        </div>
      </section>

      <section style={section}>
        <h2 style={h2}>Evidence status</h2>
        <div style={card}>
          <p style={{ margin: "0 0 8px" }}>
            <strong>Done:</strong> provider access, both paths, 10-sentence eval, latency table.
          </p>
          <p style={{ margin: "0 0 8px" }}>
            <strong>Open:</strong> blind naturalness ratings (3–5 Hindi/English speakers),
            hand-labeled segmentation ground truth, SBDS seam numbers.
          </p>
          <p style={{ ...prose, margin: 0 }}>
            Small sample, reported as raw counts, limitations stated — see RIME_EVIDENCE.md.
          </p>
        </div>
      </section>

      <section style={section}>
        <h2 style={h2}>Reproduce in 3 steps</h2>
        <div style={card}>
          <p style={{ ...prose, margin: "0 0 8px" }}>
            <strong>1.</strong> <code>pip install -r requirements.txt</code>, copy
            .env.example to .env, add RIME_API_KEY + GROQ_API_KEY.
          </p>
          <p style={{ ...prose, margin: "0 0 8px" }}>
            <strong>2.</strong> <code>py scripts/smoke_test.py</code> (provider gate), then{" "}
            <code>py scripts/run_eval.py</code> (clips + timings).
          </p>
          <p style={{ ...prose, margin: 0 }}>
            <strong>3.</strong> <code>py scripts/make_rater_packet.py</code>, collect blind
            ratings, score with <code>py scripts/bonus_segmentation.py</code>.
          </p>
        </div>
      </section>

      <footer style={{ marginTop: 24, ...prose, fontSize: 13 }}>
        LinguaSwitch — Rime TTS track demo. Audio and timings regenerate locally via scripts/.
      </footer>
    </main>
  );
}
