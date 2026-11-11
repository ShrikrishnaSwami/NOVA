"""Containerized event observer used by NOVA's local Compose cluster."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal

import nats
from nats.js.api import RetentionPolicy, StorageType, StreamConfig

from nova.distributed.bus import EVENT_SUBJECT, STREAM_NAME

logging.basicConfig(
    level=os.getenv("NOVA_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [nova-event-worker] %(message)s",
)
logger = logging.getLogger("nova.distributed.worker")


async def run() -> None:
    broker_url = os.getenv("NOVA_NATS_URL", "nats://nats:4222")
    connection = await nats.connect(
        servers=[broker_url],
        name=os.getenv("NOVA_NODE_ID", "nova-event-worker-1"),
        reconnect_time_wait=2,
        max_reconnect_attempts=-1,
    )
    jetstream = connection.jetstream()

    try:
        await jetstream.stream_info(STREAM_NAME)
    except Exception:
        try:
            await jetstream.add_stream(
                config=StreamConfig(
                    name=STREAM_NAME,
                    subjects=[EVENT_SUBJECT],
                    retention=RetentionPolicy.LIMITS,
                    storage=StorageType.FILE,
                    max_age=7 * 24 * 60 * 60,
                )
            )
        except Exception:
            await jetstream.stream_info(STREAM_NAME)

    subscription = await jetstream.pull_subscribe(
        EVENT_SUBJECT,
        durable="nova-event-observer",
        stream=STREAM_NAME,
    )
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stopping.set)
        except NotImplementedError:
            pass

    logger.info("Connected to %s; observing persisted NOVA events.", broker_url)
    try:
        while not stopping.is_set():
            try:
                messages = await subscription.fetch(batch=10, timeout=1)
            except asyncio.TimeoutError:
                continue
            for message in messages:
                try:
                    event = json.loads(message.data.decode("utf-8"))
                    logger.info(
                        "event=%s id=%s source=%s",
                        event.get("event_type", message.subject),
                        event.get("event_id", "unknown"),
                        event.get("source", "unknown"),
                    )
                    await message.ack()
                except Exception:
                    logger.exception("Could not process event on %s", message.subject)
                    await message.nak()
    finally:
        await connection.drain()
        logger.info("Event observer stopped.")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
