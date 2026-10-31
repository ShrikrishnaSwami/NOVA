"""NOVA API application entry point."""

from fastapi import FastAPI

from nova.api.chat import router as chat_router
from nova.config import get_settings

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Local API and provider-independent AI foundation for NOVA.",
)

app.include_router(chat_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Return a lightweight process health response."""
    return {
        "status": "ok",
        "application": settings.app_name,
        "environment": settings.environment,
    }
