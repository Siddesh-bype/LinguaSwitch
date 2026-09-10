"use client";

import { useEffect, useState, type CSSProperties } from "react";

const API = "http://localhost:8000";

type Sentence = { id: number; text: string };
type Segment = { lang: "hin" | "eng"; text: string; speaker?: string };
type NativeResult = { audio_b64: string; ttfa_ms: number; total_ms: number; api_calls: number };
type BaselineResult = NativeResult & { segment_ms: number; segments: Segment[] };
type ApiError = { error: string; provider: string; fallback: string };
type PathState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; data: NativeResult | BaselineResult; audioUrl: string }
  | { status: "error"; err: ApiError };

async function speak(path: "native" | "baseline", text: string): Promise<PathState> {
  try {
    const res = await fetch(`${API}/api/speak/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      const err = (await res.json().catch(() => null)) as ApiError | null;
      return {
        status: "error",
        err: err ?? { error: `HTTP ${res.status}`, provider: "unknown", fallback: "none" },
      };
    }
    const data = (await res.json()) as NativeResult | BaselineResult;
    const bytes = Uint8Array.from(atob(data.audio_b64), (c) => c.charCodeAt(0));
    return {
      status: "ok",
      data,
      audioUrl: URL.createObjectURL(new Blob([bytes], { type: "audio/wav" })),
    };
  } catch (e) {
    return {
      status: "error",
      err: { error: String(e), provider: "network", fallback: "none" },
    };
  }
}

const card: CSSProperties = {
  flex: 1,
  minWidth: 300,
  background: "var(--card)",
  borderRadius: 12,
  padding: 20,
};
const btn: CSSProperties = {
  padding: "12px 16px",
  minHeight: 44,
  fontSize: 15,
  fontWeight: 700,
  borderRadius: 8,
  border: "none",
  cursor: "pointer",
  color: "#fff",
};
const th: CSSProperties = { textAlign: "left", padding: "8px 12px", color: "var(--ink-muted)" };
const td: CSSProperties = { padding: "8px 12px", fontVariantNumeric: "tabular-nums" };
const prose: CSSProperties = { color: "var(--ink-muted)", maxWidth: "65ch" };
const field: CSSProperties = {
  marginLeft: 8,
  minHeight: 44,
  background: "var(--surface)",
  color: "var(--ink)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: 8,
};

function ResultCard({ title, state }: { title: string; state: PathState }) {
  const isBaseline = (s: PathState): s is { status: "ok"; data: BaselineResult; audioUrl: string } =>
    s.status === "ok" && "segments" in s.data;

  return (
    <div style={card}>
      <h3 style={{ margin: "0 0 12px", fontSize: 18 }}>{title}</h3>
      {state.status === "loading" && <p role="status">Generating audio…</p>}
      {state.status === "error" && (
        <div role="alert" style={{ borderLeft: "4px solid var(--accent)", padding: 12, color: "var(--ink)" }}>
          <strong>Generation failed: </strong>
          <span style={{ maxWidth: "65ch", display: "inline-block", overflowWrap: "anywhere" }}>{state.err.error}</span>
          <p style={{ margin: "8px 0 0", maxWidth: "65ch" }}>
            Provider: {state.err.provider} (fallback: {state.err.fallback})
          </p>
        </div>
      )}
      {state.status === "ok" && (
        <div className="fade-in" key={state.audioUrl}>
          <audio controls style={{ width: "100%" }} src={state.audioUrl} />
          <table style={{ marginTop: 12, borderCollapse: "collapse", width: "100%" }}>
            <tbody>
              <tr>
                <th style={th}>TTFA</th>
                <td style={td}>{state.data.ttfa_ms} ms</td>
              </tr>
              {isBaseline(state) && (
                <tr>
                  <th style={th}>Router time</th>
                  <td style={td}>{state.data.segment_ms} ms</td>
                </tr>
              )}
              <tr>
                <th style={th}>Total time</th>
                <td style={td}>{state.data.total_ms} ms</td>
              </tr>
              <tr>
                <th style={th}>API calls</th>
                <td style={td}>{state.data.api_calls}</td>
              </tr>
            </tbody>
          </table>
          {isBaseline(state) && (
            <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 8 }}>
              {state.data.segments.map((seg, i) => (
                <span
                  key={i}
                  style={{
                    padding: "8px 12px",
                    borderRadius: 8,
                    fontSize: 13,
                    background: "var(--surface)",
                    color: "var(--ink)",
                    border: "1px solid var(--border)",
                    maxWidth: "100%",
                    overflowWrap: "anywhere",
                  }}
                >
                  <strong>{seg.lang}</strong>
                  {seg.speaker ? ` · ${seg.speaker}` : ""}: {seg.text}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      {state.status === "idle" && <p style={{ ...prose }}>Press a button to generate.</p>}
    </div>
  );
}

export default function Home() {
  const [sentences, setSentences] = useState<Sentence[]>([]);
  const [selected, setSelected] = useState("");
  const [custom, setCustom] = useState("");
  const [a, setA] = useState<PathState>({ status: "idle" });
  const [b, setB] = useState<PathState>({ status: "idle" });

  useEffect(() => {
    fetch(`${API}/api/sentences`)
      .then((r) => r.json())
      .then((d: { sentences: Sentence[] }) => {
        setSentences(d.sentences);
        if (d.sentences[0]) setSelected(String(d.sentences[0].id));
      })
      .catch(() => setSentences([]));
  }, []);

  const text = custom.trim() || sentences.find((s) => String(s.id) === selected)?.text || "";

  const run = (path: "native" | "baseline") => {
    if (!text) return;
    const setter = path === "native" ? setA : setB;
    setter({ status: "loading" });
    speak(path, text).then(setter);
  };

  return (
    <main style={{ maxWidth: 1000, margin: "0 auto", padding: 24 }}>
      <h1 style={{ margin: "0 0 8px", fontSize: 28 }}>Hinglish TTS — A/B Comparison</h1>
      <p style={prose}>Path A: native code-switching · Path B: segment &amp; route</p>

      <div style={{ ...card, marginBottom: 16 }}>
        {sentences.length === 0 ? (
          <p style={prose} role="status">
            <strong>No test sentences loaded. </strong>
            Start the backend with `uvicorn backend.main:app --port 8000`, then reload this page.
          </p>
        ) : (
        <>
        <label style={{ display: "block", marginBottom: 8 }}>
          Test sentence
          <select value={selected} onChange={(e) => setSelected(e.target.value)} style={field}>
            {sentences.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id}. {s.text}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "block", marginBottom: 12 }}>
          Or type custom Hinglish
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="ye product damaged hai, I want a return"
            style={{ ...field, width: 320 }}
          />
        </label>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <button style={btn} onClick={() => run("native")} disabled={a.status === "loading" || !text}>
            Path A — Native (Rime code-switching)
          </button>
          <button style={btn} onClick={() => run("baseline")} disabled={b.status === "loading" || !text}>
            Path B — Segment &amp; Route (LLM router)
          </button>
        </div>
        </>
        )}
      </div>

      <h2 style={{ margin: "0 0 12px", fontSize: 20 }}>Results</h2>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <ResultCard title="Path A — Native" state={a} />
        <ResultCard title="Path B — Segment &amp; Route" state={b} />
      </div>

      <footer style={{ marginTop: 24, ...prose, fontSize: 13 }}>
        LinguaSwitch — Rime TTS track demo. Backend: {API}. Audio and timings regenerate locally via scripts/.
      </footer>
    </main>
  );
}
