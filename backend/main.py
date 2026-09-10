"""FastAPI app for the LinguaSwitch native-vs-baseline TTS demo."""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, streaming
from .agent_routes import router as agent_router
from .metrics_routes import router as metrics_router
from .ratings_routes import router as ratings_router
from .routes import router

app = FastAPI(title="LinguaSwitch TTS backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(agent_router)
app.include_router(metrics_router)
app.include_router(ratings_router)
app.include_router(streaming.ws_router)


@app.get("/api/health")
def health():
    """Liveness + pinned-config probe (no secrets, no network calls).

    Frontend and CI use this to check the backend is up and which
    model/voices it is pinned to. Never includes API keys.
    """
    return {
        "status": "ok",
        "service": "linguaswitch-backend",
        "rime_model": config.RIME_MODEL,
        "speakers": {"hin": config.RIME_SPEAKER_HIN, "eng": config.RIME_SPEAKER_ENG},
        "langs": {"hin": config.RIME_LANG_HIN, "eng": config.RIME_LANG_ENG},
        "router_model": config.GROQ_ROUTER_MODEL,
        "rime_configured": bool(config.RIME_API_KEY),
        "groq_configured": bool(config.GROQ_API_KEY),
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
