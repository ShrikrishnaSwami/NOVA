"""Application entry point for NOVA's local API and background services."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from nova.api.chat import router as chat_router
from nova.api.computer import router as computer_router
from nova.api.memory import router as memory_router
from nova.api.tasks import router as tasks_router
from nova.api.runtime import router as runtime_router
from nova.config import get_settings
from nova.core.ai.factory import close_provider, get_provider
from nova.core.memory import MemoryStore
from nova.core.tasks import TaskScheduler, TaskStore
from nova.core.runtime import SystemStateMonitor
from nova.core.runtime.tools import SimulationCore, build_default_registry

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_provider()
    MemoryStore(settings.memory_db_path).initialize()
    scheduler = TaskScheduler(TaskStore(settings.memory_db_path))
    scheduler.start()
    monitor = SystemStateMonitor(interval_seconds=2.0)
    await monitor.start()
    app.state.task_scheduler = scheduler
    app.state.system_monitor = monitor
    app.state.simulation_core = SimulationCore()
    app.state.tool_registry = build_default_registry(app.state.simulation_core)
    try:
        yield
    finally:
        await monitor.stop()
        scheduler.stop()
        await close_provider()


app = FastAPI(
    title=settings.app_name,
    version="0.7.0",
    description="Windows-integrated local API, AI, memory, permissioned automation, and scheduled tasks for NOVA.",
    lifespan=lifespan,
)
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(computer_router)
app.include_router(tasks_router)
app.include_router(runtime_router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "application": settings.app_name, "environment": settings.environment}
