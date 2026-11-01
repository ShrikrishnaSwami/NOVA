"""NOVA API application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from nova.api.chat import router as chat_router
from nova.config import get_settings
from nova.core.ai.factory import close_provider, get_provider

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_provider()
    yield
    await close_provider()


app = FastAPI(title=settings.app_name, version="0.4.0", description="Local API and provider-independent AI foundation for NOVA.", lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "application": settings.app_name, "environment": settings.environment}
