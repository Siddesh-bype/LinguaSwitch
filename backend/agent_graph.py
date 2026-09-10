"""LangGraph voice agent: native (Path A) vs segment-and-route (Path B).

Graph: input -> segment -> tts_native -> tts_routed -> metrics.

- segment: LangChain structured-output router (ChatGroq on
  config.GROQ_ROUTER_MODEL) with a Pydantic schema, reusing the
  SYSTEM/EXAMPLES prompt style from backend/segmenter.py. Falls back to
  backend/segmenter.py on any LangChain failure.
- tts_native (Path A): backend.rime.speak with the default voice.
- tts_routed (Path B): per-segment rime.speak with config.LANG_MAP /
  config.SPEAKER_MAP, joined with backend.audio.concat_wav.
- metrics: ttfa / total / api_calls for both paths plus a
  framework-overhead note.

Both TTS paths always run (the A/B comparison needs both audios); the
routing node only feeds Path B.

run_agentic(text) executes the graph (or the same node functions
sequentially when langgraph is unavailable) and returns raw bytes +
metrics dicts; base64 encoding lives in agent_routes.py.
"""

import time
from typing import Literal, TypedDict

from pydantic import BaseModel, Field

from . import audio, config, rime, segmenter

try:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    from langchain_groq import ChatGroq
    from langgraph.graph import END, StateGraph

    _LANGGRAPH_AVAILABLE = True
except Exception:  # langchain/langgraph not installed yet -> lazy fallback
    AIMessage = HumanMessage = SystemMessage = None  # type: ignore
    ChatGroq = None  # type: ignore
    END = "end"  # type: ignore
    StateGraph = None  # type: ignore
    _LANGGRAPH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Structured-output schema for the LangChain router.
# ---------------------------------------------------------------------------


class Segment(BaseModel):
    lang: Literal["hin", "eng"]
    text: str


class RouterOutput(BaseModel):
    segments: list[Segment] = Field(description="Ordered language-tagged runs")


# ---------------------------------------------------------------------------
# Graph state.
# ---------------------------------------------------------------------------


class AgentState(TypedDict, total=False):
    text: str
    model: str | None
    segments: list[dict]
    segment_ms: int
    router_used: str
    audio_a: bytes
    metrics_a: dict
    audio_b: bytes
    metrics_b: dict
    segments_detailed: list[dict]


# ---------------------------------------------------------------------------
# Nodes.
# ---------------------------------------------------------------------------


def _langchain_segment(text: str, model: str | None) -> list[dict]:
    """Route via LangChain structured output; raises on any failure."""
    llm = ChatGroq(model=model or config.GROQ_ROUTER_MODEL)  # type: ignore[operator]
    structured = llm.with_structured_output(RouterOutput)
    messages = [SystemMessage(content=segmenter.SYSTEM)]  # type: ignore[operator]
    for user, segs in segmenter.EXAMPLES:
        messages.append(HumanMessage(content=user))  # type: ignore[operator]
        import json as _json

        messages.append(
            AIMessage(content=_json.dumps({"segments": segs}))  # type: ignore[operator]
        )
    messages.append(HumanMessage(content=text))  # type: ignore[operator]
    result = structured.invoke(messages)
    out = [{"lang": s.lang, "text": s.text} for s in result.segments]
    if not out or any(s["lang"] not in ("hin", "eng") for s in out):
        raise ValueError(f"bad segments: {out}")
    return out


def segment_node(state: AgentState) -> dict:
    """Router node: LangChain structured output, fallback to segmenter.py."""
    text = state["text"]
    model = state.get("model")
    t0 = time.perf_counter()
    try:
        if not _LANGGRAPH_AVAILABLE:
            raise ImportError("langchain/langgraph not installed")
        segs = _langchain_segment(text, model)
        router_used = "langchain"
    except Exception:
        segs, _ = segmenter.segment_timed(text, model)
        router_used = "fallback:segmenter"
    segment_ms = int((time.perf_counter() - t0) * 1000)
    return {"segments": segs, "segment_ms": segment_ms, "router_used": router_used}


def tts_native_node(state: AgentState) -> dict:
    """Path A: single native call with the default voice."""
    r = rime.speak(state["text"], config.DEFAULT_LANG)
    return {
        "audio_a": r["audio"],
        "metrics_a": {"ttfa_ms": r["ttfa_ms"], "total_ms": r["total_ms"], "api_calls": 1},
    }


def tts_routed_node(state: AgentState) -> dict:
    """Path B: per-segment TTS with per-language voice, WAVs concatenated."""
    segments = state["segments"]
    results = []
    for seg in segments:
        # A Rime voice serves one language: swap speaker per segment.
        r = rime.speak(
            seg["text"],
            config.LANG_MAP.get(seg["lang"], config.DEFAULT_LANG),
            config.SPEAKER_MAP.get(seg["lang"], config.RIME_SPEAKER),
        )
        results.append(r)
    combined = audio.concat_wav([r["audio"] for r in results])
    segment_ms = state.get("segment_ms", 0)
    detailed = [
        {
            "lang": s["lang"],
            "text": s["text"],
            "speaker": config.SPEAKER_MAP.get(s["lang"], config.RIME_SPEAKER),
            "ttfa_ms": r["ttfa_ms"],
            "total_ms": r["total_ms"],
        }
        for s, r in zip(segments, results)
    ]
    metrics_b = {
        "segment_ms": segment_ms,
        "router": state.get("router_used", "unknown"),
        "ttfa_ms": segment_ms + (results[0]["ttfa_ms"] if results else 0),
        "total_ms": segment_ms + sum(r["total_ms"] for r in results),
        "api_calls": len(segments) + 1,  # N segment TTS calls + 1 router call
    }
    return {"audio_b": combined, "metrics_b": metrics_b, "segments_detailed": detailed}


def metrics_node(state: AgentState) -> dict:
    """Attach the framework-overhead note to Path B metrics."""
    metrics_b = dict(state.get("metrics_b", {}))
    metrics_b["framework"] = "langgraph" if _LANGGRAPH_AVAILABLE else "sequential-fallback"
    metrics_b["framework_overhead_note"] = (
        "LangGraph orchestration adds graph-scheduling overhead vs the direct "
        "baseline; TTS latency dominates (segment_ms + per-segment total_ms)."
    )
    return {"metrics_b": metrics_b}


# ---------------------------------------------------------------------------
# Graph assembly (built lazily so import stays offline-safe).
# ---------------------------------------------------------------------------


def _build_graph():
    if not _LANGGRAPH_AVAILABLE:
        return None
    g: StateGraph = StateGraph(AgentState)  # type: ignore[operator]
    g.add_node("segment", segment_node)
    g.add_node("tts_native", tts_native_node)
    g.add_node("tts_routed", tts_routed_node)
    g.add_node("metrics", metrics_node)
    g.set_entry_point("segment")
    g.add_edge("segment", "tts_native")
    g.add_edge("tts_native", "tts_routed")
    g.add_edge("tts_routed", "metrics")
    g.add_edge("metrics", END)
    return g.compile()


def run_agentic(text: str, model: str | None = None) -> dict:
    """Run both TTS paths through the agent graph.

    Returns {"audio_a": bytes, "audio_b": bytes, "metrics_a": dict,
    "metrics_b": dict, "segments": [detailed per-segment dicts]}.
    Raises whatever rime/segmenter raise (routes map to 502s).
    """
    graph = _build_graph()
    if graph is not None:
        final = graph.invoke({"text": text, "model": model})
    else:  # same nodes, sequential — identical outputs without langgraph
        state: AgentState = {"text": text, "model": model}
        state.update(segment_node(state))  # type: ignore[typeddict-item]
        state.update(tts_native_node(state))  # type: ignore[typeddict-item]
        state.update(tts_routed_node(state))  # type: ignore[typeddict-item]
        state.update(metrics_node(state))  # type: ignore[typeddict-item]
        final = state
    return {
        "audio_a": final["audio_a"],
        "audio_b": final["audio_b"],
        "metrics_a": final["metrics_a"],
        "metrics_b": final["metrics_b"],
        "segments": final.get("segments_detailed", []),
    }
