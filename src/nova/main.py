"""NOVA API application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from nova.api.chat import router as chat_router
from nova.api.computer import router as computer_router
from nova.api.memory import router as memory_router
from nova.config import get_settings
from nova.core.ai.factory import close_provider, get_provider
from nova.core.memory import MemoryStore

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_provider()
    MemoryStore(settings.memory_db_path).initialize()
    yield
    await close_provider()


app = FastAPI(title=settings.app_name, version="0.5.0", description="Local API, AI, and persistent memory foundation for NOVA.", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(computer_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "application": settings.app_name, "environment": settings.environment}
