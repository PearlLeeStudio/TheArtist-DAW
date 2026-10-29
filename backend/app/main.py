import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.generate import router as generate_router
from app.routes.chords import router as chords_router
from app.routes.models import router as models_router
from app.routes.song import router as song_router
from app.routes.score_import import router as score_import_router
from app.routes.export import router as export_router
from app.routes.plan import router as plan_router
from app.mcp_server import create_mcp_server
from app.services.contracts import ContractEnvelope, capabilities

# Surface app.* INFO-level logs (model load, rerank breakdown, RAG init,
# etc.) — uvicorn's default config filters them otherwise.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

mcp_server = create_mcp_server()
mcp_app = mcp_server.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_server.session_manager.run():
        await startup_warmup()
        yield


app = FastAPI(title="TheArtist API", version="0.1.0", lifespan=lifespan)

_default_origins = "http://localhost:5173"
_allowed_origins = os.getenv("CORS_ORIGINS", _default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate_router, prefix="/api")
app.include_router(chords_router, prefix="/api")
app.include_router(models_router, prefix="/api")
app.include_router(song_router, prefix="/api")
app.include_router(score_import_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(plan_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/capabilities")
def api_capabilities() -> ContractEnvelope:
    return capabilities()


app.mount("/mcp", mcp_app)


async def startup_warmup():
    """Preload models at startup if THEARTIST_WARMUP=1."""
    if os.getenv("THEARTIST_WARMUP", "0") == "1":
        import asyncio
        from app.services.inference import TORCH_AVAILABLE, ModelRegistry
        if TORCH_AVAILABLE:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, ModelRegistry.get().warmup)
