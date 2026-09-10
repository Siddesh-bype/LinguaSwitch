"""FastAPI app for the LinguaSwitch native-vs-baseline TTS demo."""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import streaming
from .agent_routes import router as agent_router
from .metrics_routes import router as metrics_router
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
app.include_router(streaming.ws_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
