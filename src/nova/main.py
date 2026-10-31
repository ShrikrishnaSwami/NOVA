"""NOVA API application entry point."""

from fastapi import FastAPI

from nova.config import get_settings

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Local API foundation for the NOVA desktop assistant.",
)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Return a lightweight process health response."""
    return {
        "status": "ok",
        "application": settings.app_name,
        "environment": settings.environment,
    }
