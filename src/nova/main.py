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
from nova.core.computer.shell_integration import notifications_enabled, show_windows_toast

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_provider()
    MemoryStore(settings.memory_db_path).initialize()
    def notify_task(event: dict):
        if notifications_enabled():
            task = event.get("task", {})
            result = event.get("result", {})
            status = str(event.get("status", "unknown")).upper()
            title = str(task.get("title", "Scheduled task"))[:100]
            summary = "Completed successfully." if status == "SUCCESS" else str(result.get("error", "Task did not complete."))[:350]
            show_windows_toast(f"NOVA task {status.lower()}: {title}", summary)

    def notify_alert(alert: dict):
        if notifications_enabled():
            show_windows_toast(f"NOVA system {alert.get('severity', 'alert')}", str(alert.get("message", "System alert.")))

    scheduler = TaskScheduler(TaskStore(settings.memory_db_path), on_event=notify_task)
    scheduler.start()
    monitor = SystemStateMonitor(interval_seconds=2.0, on_alert=notify_alert)
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
    version="0.1.4",
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
