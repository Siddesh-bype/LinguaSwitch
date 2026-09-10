"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";

const API =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

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
type HistoryRow = {
  ts: string;
  text: string;
  a_ttfa: number | null;
  a_total: number | null;
  b_ttfa: number | null;
  b_total: number | null;
};

const HISTORY_KEY = "linguaswitch-history-v1";
const HISTORY_LIMIT = 10;
const RATER_KEY = "linguaswitch-rater";

type VoteTotals = { X: number; Y: number; same: number };
type VoteTally = {
  votes: number;
  raters: string[];
  totals: VoteTotals;
  per_question: Record<string, VoteTotals>;
};

async function fetchTally(): Promise<VoteTally | null> {
  try {
    const res = await fetch(`${API}/api/ratings/tally`);
    if (!res.ok) return null;
    return (await res.json()) as VoteTally;
  } catch {
    return null;
  }
}

async function castVote(rater: string, question: string, choice: "X" | "Y" | "same"): Promise<string | null> {
  try {
    const res = await fetch(`${API}/api/ratings/vote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rater, question, choice }),
    });
    if (!res.ok) {
      const err = (await res.json().catch(() => null)) as { error?: string } | null;
      return err?.error ?? `HTTP ${res.status}`;
    }
    return null;
  } catch (e) {
    return String(e);
  }
}

type AgenticMetricsA = { ttfa_ms: number; total_ms: number; api_calls: number };
type AgenticMetricsB = AgenticMetricsA & {
  segment_ms: number;
  router: string;
  framework: string;
  framework_overhead_note: string;
};
type AgenticSegment = { lang: "hin" | "eng"; text: string; speaker: string; ttfa_ms: number; total_ms: number };
type AgenticResult = {
  audio_a_b64: string;
  audio_b_b64: string;
  metrics_a: AgenticMetricsA;
  metrics_b: AgenticMetricsB;
  segments: AgenticSegment[];
};
type AgenticState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; data: AgenticResult; urlA: string; urlB: string }
  | { status: "error"; err: ApiError };

function wavUrl(b64: string): string {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  return URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
}

async function runAgentic(text: string): Promise<AgenticState> {
  try {
    const res = await fetch(`${API}/api/speak/agentic`, {
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
    const data = (await res.json()) as AgenticResult;
    return { status: "ok", data, urlA: wavUrl(data.audio_a_b64), urlB: wavUrl(data.audio_b_b64) };
  } catch (e) {
    return {
      status: "error",
      err: { error: String(e), provider: "network", fallback: "none" },
    };
  }
}

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

function loadHistory(): HistoryRow[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as HistoryRow[];
    return Array.isArray(parsed) ? parsed.slice(0, HISTORY_LIMIT) : [];
  } catch {
    return [];
  }
}

const card: CSSProperties = {
  flex: 1,
  minWidth: 300,
  minHeight: 280,
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
const ghostBtn: CSSProperties = {
  ...btn,
  background: "var(--surface)",
  color: "var(--ink)",
  border: "1px solid var(--border)",
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

function LatencyBars({ a, b }: { a: PathState; b: PathState }) {
  if (a.status !== "ok" || b.status !== "ok") return null;
  const max = Math.max(a.data.total_ms, b.data.total_ms, 1);
  const delta = b.data.total_ms - a.data.total_ms;
  const rows: Array<{ label: string; total: number; ttfa: number; color: string }> = [
    { label: "A total", total: a.data.total_ms, ttfa: a.data.ttfa_ms, color: "var(--accent)" },
    { label: "B total", total: b.data.total_ms, ttfa: b.data.ttfa_ms, color: "var(--ink)" },
  ];
  return (
    <div style={{ ...card, marginTop: 16 }} aria-label="Latency comparison">
      <h3 style={{ margin: "0 0 12px", fontSize: 16 }}>Latency head-to-head</h3>
      {rows.map((r) => (
        <div key={r.label} style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
            <span>{r.label}</span>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>
              {r.total} ms (TTFA {r.ttfa} ms)
            </span>
          </div>
          <div style={{ height: 12, borderRadius: 8, background: "var(--surface)", overflow: "hidden" }}>
            <div
              style={{
                width: `${Math.max(2, Math.round((r.total / max) * 100))}%`,
                height: "100%",
                background: r.color,
              }}
            />
          </div>
        </div>
      ))}
      <p style={{ ...prose, fontSize: 13, margin: "8px 0 0" }} role="status">
        {delta === 0
          ? "Tie on total latency."
          : delta > 0
            ? `Native (A) is ${delta} ms faster end-to-end this run.`
            : `Baseline (B) is ${-delta} ms faster end-to-end this run.`}
      </p>
    </div>
  );
}

function ResultCard({ title, state, blindLabel }: { title: string; state: PathState; blindLabel?: string }) {
  const isBaseline = (s: PathState): s is { status: "ok"; data: BaselineResult; audioUrl: string } =>
    s.status === "ok" && "segments" in s.data;

  return (
    <div style={card}>
      <h3 style={{ margin: "0 0 12px", fontSize: 18 }}>{blindLabel ?? title}</h3>
      {state.status === "loading" && <p role="status">Generating audioΓÇª</p>}
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
          {isBaseline(state) && !blindLabel && (
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
                  {seg.speaker ? ` ┬╖ ${seg.speaker}` : ""}: {seg.text}
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
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  const [blind, setBlind] = useState(false);
  const [blindMap, setBlindMap] = useState<{ x: "a" | "b" } | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [agentic, setAgentic] = useState<AgenticState>({ status: "idle" });
  const [rater, setRater] = useState("");
  const [tally, setTally] = useState<VoteTally | null>(null);
  const [voting, setVoting] = useState(false);
  const [voteMsg, setVoteMsg] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/api/sentences`)
      .then((r) => r.json())
      .then((d: { sentences: Sentence[] }) => {
        setSentences(d.sentences);
        if (d.sentences[0]) setSelected(String(d.sentences[0].id));
      })
      .catch(() => setSentences([]));
    // Health probe is best-effort: older backends 404, offline backends throw.
    fetch(`${API}/api/health`)
      .then((r) => setBackendUp(r.ok))
      .catch(() => setBackendUp(false));
    setHistory(loadHistory());
    try {
      setRater(localStorage.getItem(RATER_KEY) ?? "");
    } catch {
      /* private mode: rater name just won't persist */
    }
    fetchTally().then(setTally);
  }, []);

  const text = custom.trim() || sentences.find((s) => String(s.id) === selected)?.text || "";
  const busy = a.status === "loading" || b.status === "loading";
  const agenticBusy = agentic.status === "loading";

  const pushHistory = useCallback((na: PathState, nb: PathState, t: string) => {
    if (na.status !== "ok" || nb.status !== "ok") return;
    const row: HistoryRow = {
      ts: new Date().toISOString(),
      text: t.slice(0, 80),
      a_ttfa: na.data.ttfa_ms,
      a_total: na.data.total_ms,
      b_ttfa: nb.data.ttfa_ms,
      b_total: nb.data.total_ms,
    };
    setHistory((prev) => {
      const next = [row, ...prev].slice(0, HISTORY_LIMIT);
      try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
      } catch {
        /* private-mode storage: history just won't persist */
      }
      return next;
    });
  }, []);

  const run = (path: "native" | "baseline") => {
    if (!text || busy) return;
    if (blind && !blindMap) setBlindMap({ x: Math.random() < 0.5 ? "a" : "b" });
    const setter = path === "native" ? setA : setB;
    setter({ status: "loading" });
    speak(path, text).then((s) => {
      setter(s);
      const other = path === "native" ? b : a;
      if (s.status === "ok" && other.status === "ok") pushHistory(path === "native" ? s : other, path === "native" ? other : s, text);
    });
  };

  const runBoth = () => {
    if (!text || busy) return;
    if (blind) setBlindMap({ x: Math.random() < 0.5 ? "a" : "b" });
    setA({ status: "loading" });
    setB({ status: "loading" });
    Promise.all([speak("native", text), speak("baseline", text)]).then(([na, nb]) => {
      setA(na);
      setB(nb);
      pushHistory(na, nb, text);
    });
  };

  const runAgenticBoth = () => {
    if (!text || busy || agenticBusy) return;
    setAgentic({ status: "loading" });
    runAgentic(text).then(setAgentic);
  };

  // Live straw-poll votes (server tally). The official record stays the
  // rater packet (responses.csv); this is the casual demo counterpart.
  // Question key tracks the current sentence so votes group per sentence.
  const voteQuestion = custom.trim() ? "demo-custom" : selected ? `demo-s${selected}` : "";
  const canVote = blind && a.status === "ok" && b.status === "ok" && !voting && voteQuestion !== "";

  const vote = (choice: "X" | "Y" | "same") => {
    const name = rater.trim();
    if (!name) {
      setVoteMsg("Type a rater name first (it labels your votes in the tally).");
      return;
    }
    if (!canVote) return;
    setVoting(true);
    setVoteMsg(null);
    try {
      localStorage.setItem(RATER_KEY, name);
    } catch {
      /* ignore */
    }
    castVote(name, voteQuestion, choice).then((err) => {
      setVoting(false);
      if (err) {
        setVoteMsg(`Vote failed: ${err}`);
        return;
      }
      setVoteMsg(`Recorded ${choice} for ${voteQuestion}. Revoting overwrites your last vote.`);
      fetchTally().then(setTally);
    });
  };

  const winner = useMemo(() => {
    if (a.status !== "ok" || b.status !== "ok") return null;
    if (a.data.total_ms === b.data.total_ms) return "tie";
    return a.data.total_ms < b.data.total_ms ? "a" : "b";
  }, [a, b]);

  const exportCsv = () => {
    const lines = ["ts,text,a_ttfa_ms,a_total_ms,b_ttfa_ms,b_total_ms", ...history.map((h) => [h.ts, JSON.stringify(h.text), h.a_ttfa ?? "", h.a_total ?? "", h.b_ttfa ?? "", h.b_total ?? ""].join(","))];
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "linguaswitch-history.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  // In blind mode X/Y hides which clip is native until Reveal.
  const titles = blind && blindMap ? { a: blindMap.x === "a" ? "Clip X" : "Clip Y", b: blindMap.x === "a" ? "Clip Y" : "Clip X" } : null;

  return (
    <main style={{ maxWidth: 1000, margin: "0 auto", padding: 24 }}>
      <p style={{ margin: "0 0 12px" }}>
        <Link href="/" style={{ color: "var(--ink-muted)" }}>
          Back to LinguaSwitch
        </Link>
      </p>
      <h1 style={{ margin: "0 0 8px", fontSize: 28 }}>Hinglish TTS ΓÇö A/B Comparison</h1>
      <p style={prose}>
        Path A: native code-switching ┬╖ Path B: segment &amp; route ┬╖ Backend: {API} ┬╖{" "}
        {backendUp === null ? "checking backendΓÇª" : backendUp ? "backend reachable" : "backend unreachable ΓÇö start `uvicorn backend.main:app --port 8000`"}
      </p>

      <div style={{ ...card, marginBottom: 16, marginTop: 16 }}>
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
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <button style={btn} onClick={() => run("native")} disabled={busy || !text}>
            Path A ΓÇö Native (Rime code-switching)
          </button>
          <button style={btn} onClick={() => run("baseline")} disabled={busy || !text}>
            Path B ΓÇö Segment &amp; Route (LLM router)
          </button>
          <button style={btn} onClick={runBoth} disabled={busy || !text}>
            Run both (fair race)
          </button>
          <button style={{ ...btn, background: "#7c3aed" }} onClick={runAgenticBoth} disabled={busy || agenticBusy || !text}>
            Run agentic (LangGraph)
          </button>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 14 }}>
            <input type="checkbox" checked={blind} onChange={(e) => { setBlind(e.target.checked); setBlindMap(null); }} style={{ width: 20, height: 20 }} />
            Blind mode (hide A/B labels)
          </label>
        </div>
        {blind && (
          <p style={{ ...prose, fontSize: 13, margin: "12px 0 0" }}>
            Blind rating: listen to X and Y, decide which sounds more natural, then{" "}
            <button style={{ ...ghostBtn, minHeight: 44, padding: "8px 12px" }} onClick={() => setBlind(false)}>
              Reveal labels
            </button>
          </p>
        )}
        </>
        )}
      </div>

      <h2 style={{ margin: "0 0 12px", fontSize: 20 }}>
        Results{winner ? ` ΓÇö ${winner === "tie" ? "tie" : winner === "a" ? "A (native) faster" : "B (baseline) faster"} this run` : ""}
      </h2>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <ResultCard title="Path A ΓÇö Native" state={a} blindLabel={titles?.a} />
        <ResultCard title="Path B ΓÇö Segment &amp; Route" state={b} blindLabel={titles?.b} />
      </div>

      <LatencyBars a={a} b={b} />

      <div style={{ ...card, marginTop: 16 }}>
        <h3 style={{ margin: "0 0 8px", fontSize: 16 }}>Live straw poll (blind votes)</h3>
        <p style={{ ...prose, fontSize: 13 }}>
          Which clip sounds more natural? Votes post to the server tally below. The official record stays the rater packet
          (`responses.csv`); this is the casual demo counterpart. One vote per rater per sentence - revoting overwrites.
        </p>
        {!blind && (
          <p style={{ ...prose, fontSize: 13 }} role="status">
            Enable blind mode above first, so X/Y labels hide which clip is which.
          </p>
        )}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center", marginTop: 12 }}>
          <label style={{ fontSize: 14 }}>
            Rater
            <input
              value={rater}
              onChange={(e) => setRater(e.target.value)}
              placeholder="yourname"
              style={{ ...field, width: 160 }}
            />
          </label>
          {(["X", "Y", "same"] as const).map((c) => (
            <button key={c} style={ghostBtn} onClick={() => vote(c)} disabled={!canVote}>
              Vote {c}
            </button>
          ))}
        </div>
        {voteMsg && (
          <p style={{ ...prose, fontSize: 13 }} role="status">{voteMsg}</p>
        )}
        {tally ? (
          <p style={{ ...prose, fontSize: 13, margin: "8px 0 0" }} role="status">
            Server tally: {tally.votes} votes from {tally.raters.length} rater(s) - X {tally.totals.X}, Y {tally.totals.Y}, same {tally.totals.same}.
          </p>
        ) : (
          <p style={{ ...prose, fontSize: 13 }} role="status">
            Tally unavailable (older backend without the ratings API, or backend unreachable).
          </p>
        )}
      </div>

      <div style={{ ...card, marginTop: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <h3 style={{ margin: 0, fontSize: 16 }}>Run history (last {HISTORY_LIMIT}, this browser only)</h3>
          <div style={{ display: "flex", gap: 8 }}>
            <button style={{ ...ghostBtn, minHeight: 44, padding: "8px 12px" }} onClick={exportCsv} disabled={history.length === 0}>
              Export CSV
            </button>
            <button
              style={{ ...ghostBtn, minHeight: 44, padding: "8px 12px" }}
              onClick={() => { setHistory([]); try { localStorage.removeItem(HISTORY_KEY); } catch { /* ignore */ } }}
              disabled={history.length === 0}
            >
              Clear
            </button>
          </div>
        </div>
        {history.length === 0 ? (
          <p style={{ ...prose, margin: "12px 0 0" }}>Run both paths once to start a same-browser latency log.</p>
        ) : (
          <div style={{ overflowX: "auto", marginTop: 12 }}>
            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={th}>Time</th>
                  <th style={th}>Text</th>
                  <th style={th}>A total</th>
                  <th style={th}>B total</th>
                  <th style={th}>╬ö (BΓêÆA)</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h, i) => (
                  <tr key={`${h.ts}-${i}`}>
                    <td style={td}>{new Date(h.ts).toLocaleTimeString()}</td>
                    <td style={{ ...td, maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.text}</td>
                    <td style={td}>{h.a_total ?? "ΓÇö"} ms</td>
                    <td style={td}>{h.b_total ?? "ΓÇö"} ms</td>
                    <td style={td}>{h.a_total != null && h.b_total != null ? `${h.b_total - h.a_total} ms` : "ΓÇö"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <h2 style={{ margin: "24px 0 12px", fontSize: 20 }}>Agentic run (LangGraph, both paths in one call)</h2>
      <div style={{ ...card, marginBottom: 16 }}>
        {agentic.status === "idle" && (
          <p style={{ ...prose }}>Runs the LangGraph voice agent on the same text: structured-output router, native Path A, routed Path B, metrics.</p>
        )}
        {agentic.status === "loading" && <p role="status">Running agent (router + both TTS paths)...</p>}
        {agentic.status === "error" && (
          <div role="alert" style={{ borderLeft: "4px solid var(--accent)", padding: 12, color: "var(--ink)" }}>
            <strong>Agent run failed: </strong>
            <span style={{ maxWidth: "65ch", display: "inline-block", overflowWrap: "anywhere" }}>{agentic.err.error}</span>
            <p style={{ margin: "8px 0 0", maxWidth: "65ch" }}>
              Provider: {agentic.err.provider} (fallback: {agentic.err.fallback})
            </p>
          </div>
        )}
        {agentic.status === "ok" && (
          <div className="fade-in" key={agentic.urlA}>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 260 }}>
                <h3 style={{ margin: "0 0 8px", fontSize: 16 }}>Agent Path A - native</h3>
                <audio controls style={{ width: "100%" }} src={agentic.urlA} />
                <p style={{ ...prose, fontSize: 13 }}>
                  TTFA {agentic.data.metrics_a.ttfa_ms} ms - total {agentic.data.metrics_a.total_ms} ms - {agentic.data.metrics_a.api_calls} call
                </p>
              </div>
              <div style={{ flex: 1, minWidth: 260 }}>
                <h3 style={{ margin: "0 0 8px", fontSize: 16 }}>Agent Path B - routed</h3>
                <audio controls style={{ width: "100%" }} src={agentic.urlB} />
                <p style={{ ...prose, fontSize: 13 }}>
                  TTFA {agentic.data.metrics_b.ttfa_ms} ms - total {agentic.data.metrics_b.total_ms} ms - {agentic.data.metrics_b.api_calls} calls
                  (router {agentic.data.metrics_b.segment_ms} ms via {agentic.data.metrics_b.router}, {agentic.data.metrics_b.framework})
                </p>
              </div>
            </div>
            <p style={{ ...prose, fontSize: 13 }}>{agentic.data.metrics_b.framework_overhead_note}</p>
            <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 8 }}>
              {agentic.data.segments.map((seg, i) => (
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
                  <strong>{seg.lang}</strong> via {seg.speaker}: {seg.text}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <footer style={{ marginTop: 24, ...prose, fontSize: 13 }}>
        LinguaSwitch ΓÇö Rime TTS track demo. Backend: {API} (override with NEXT_PUBLIC_API_BASE). Audio and timings regenerate locally via scripts/.
      </footer>
    </main>
  );
}
