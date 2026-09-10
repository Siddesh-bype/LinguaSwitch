"""Agentic route: LangGraph voice agent (Path A + Path B in one call)."""
import base64

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from .agent_graph import run_agentic
from .routes import MAX_TEXT_CHARS

router = APIRouter(prefix="/api")


class AgenticRequest(BaseModel):
    text: str
    router_model: str | None = None

    @field_validator("text")
    @classmethod
    def text_must_be_speakable(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text must not be empty")
        if len(v.strip()) > MAX_TEXT_CHARS:
            raise ValueError(f"text must be <= {MAX_TEXT_CHARS} characters")
        return v


@router.post("/speak/agentic")
def speak_agentic(req: AgenticRequest):
    try:
        out = run_agentic(req.text, req.router_model)
    except Exception as e:
        msg = str(e)
        provider = "agentic"
        lowered = msg.lower()
        if "groq" in lowered or "segment" in lowered:
            provider = "groq"
        elif "rime" in lowered or "tts" in lowered:
            provider = "rime"
        return JSONResponse(
            status_code=502, content={"error": msg, "provider": provider, "fallback": "none"}
        )
    return {
        "audio_a_b64": base64.b64encode(out["audio_a"]).decode(),
        "audio_b_b64": base64.b64encode(out["audio_b"]).decode(),
        "metrics_a": out["metrics_a"],
        "metrics_b": out["metrics_b"],
        "segments": out["segments"],
    }
