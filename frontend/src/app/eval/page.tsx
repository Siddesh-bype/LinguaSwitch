"use client";

import Link from "next/link";
import { useEffect, useState, type CSSProperties } from "react";

const API =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

type SentenceRow = {
  sentence_id: number;
  a_ttfa_ms: number;
  a_total_ms: number;
  b_ttfa_ms: number;
  b_total_ms: number;
  b_segment_ms: number;
  b_segments: number;
  delta_total_ms: number;
};
type Summary = {
  n_sentences: number;
  avg_a_ttfa_ms: number;
  avg_a_total_ms: number;
  avg_b_ttfa_ms: number;
  avg_b_total_ms: number;
  native_wins: number;
  per_sentence: SentenceRow[];
};
type PageState =
  | { status: "loading" }
  | { status: "empty"; hint: string }
  | { status: "ok"; data: Summary };

const card: CSSProperties = {
  background: "var(--card)",
  borderRadius: 12,
  padding: 20,
};
const th: CSSProperties = { textAlign: "left", padding: "8px 12px", color: "var(--ink-muted)" };
const td: CSSProperties = { padding: "8px 12px", fontVariantNumeric: "tabular-nums" };
const prose: CSSProperties = { color: "var(--ink-muted)", maxWidth: "65ch" };

function AvgBars({ data }: { data: Summary }) {
  const max = Math.max(data.avg_a_total_ms, data.avg_b_total_ms, 1);
  const rows = [
    { label: "Native avg total", ms: data.avg_a_total_ms, color: "var(--accent)" },
    { label: "Baseline avg total", ms: data.avg_b_total_ms, color: "var(--ink)" },
  ];
  return (
    <div aria-label="Average latency comparison">
      {rows.map((r) => (
        <div key={r.label} style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
            <span>{r.label}</span>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{r.ms} ms</span>
          </div>
          <div style={{ height: 12, borderRadius: 8, background: "var(--surface)", overflow: "hidden" }}>
            <div
              style={{
                width: `${Math.max(2, Math.round((r.ms / max) * 100))}%`,
                height: "100%",
                background: r.color,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function EvalPage() {
  const [state, setState] = useState<PageState>({ status: "loading" });

  useEffect(() => {
    fetch(`${API}/api/eval/summary`)
      .then((r) => {
        if (r.status === 404) {
          return r.json().then((b: { error: string }) => setState({ status: "empty", hint: b.error }));
        }
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json().then((d: Summary) => setState({ status: "ok", data: d }));
      })
      .catch(() => setState({ status: "empty", hint: "Backend unreachable - start `uvicorn backend.main:app --port 8000`." }));
  }, []);

  return (
    <main style={{ maxWidth: 1000, margin: "0 auto", padding: 24 }}>
      <p style={{ margin: "0 0 12px" }}>
        <Link href="/" style={{ color: "var(--ink-muted)" }}>
          Back to LinguaSwitch
        </Link>{" "}
        -{" "}
        <Link href="/demo" style={{ color: "var(--ink-muted)" }}>
          Demo
        </Link>
      </p>
      <h1 style={{ margin: "0 0 8px", fontSize: 28 }}>Eval dashboard</h1>
      <p style={prose}>
        Latest measured A/B per sentence (latest row per sentence/path wins, same rule as `run_eval.py`). Same numbers as
        `scripts/export_summary.py`. Backend: {API}.
      </p>

      {state.status === "loading" && <p role="status">Loading eval summary...</p>}

      {state.status === "empty" && (
        <div style={{ ...card, marginTop: 16 }}>
          <p style={prose} role="status">
            <strong>No eval data to show. </strong>
            {state.hint}
          </p>
        </div>
      )}

      {state.status === "ok" && (
        <>
          <div style={{ ...card, marginTop: 16 }}>
            <h2 style={{ margin: "0 0 12px", fontSize: 18 }}>
              {state.data.n_sentences} sentences - native wins {state.data.native_wins}/{state.data.n_sentences} on total latency
            </h2>
            <AvgBars data={state.data} />
            <p style={{ ...prose, fontSize: 13 }} role="status">
              Avg TTFA: native {state.data.avg_a_ttfa_ms} ms vs baseline {state.data.avg_b_ttfa_ms} ms. Avg total: native{" "}
              {state.data.avg_a_total_ms} ms vs baseline {state.data.avg_b_total_ms} ms.
            </p>
          </div>

          <div style={{ ...card, marginTop: 16 }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
                <thead>
                  <tr>
                    <th style={th}>#</th>
                    <th style={th}>A total</th>
                    <th style={th}>B total</th>
                    <th style={th}>B segs</th>
                    <th style={th}>A faster by</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.per_sentence.map((row) => (
                    <tr key={row.sentence_id}>
                      <td style={td}>{row.sentence_id}</td>
                      <td style={td}>{row.a_total_ms} ms</td>
                      <td style={td}>{row.b_total_ms} ms</td>
                      <td style={td}>{row.b_segments}</td>
                      <td style={td}>{row.b_total_ms - row.a_total_ms} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      <footer style={{ marginTop: 24, ...prose, fontSize: 13 }}>
        Regenerate with `py scripts/run_eval.py`, then reload this page.
      </footer>
    </main>
  );
}
