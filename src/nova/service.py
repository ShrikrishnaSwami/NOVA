"""Managed local API process for the NOVA desktop session."""
from __future__ import annotations

import uvicorn

from nova.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "nova.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.casefold(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
