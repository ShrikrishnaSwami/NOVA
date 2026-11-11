# NOVA local distributed runtime

**Status:** Experimental foundation, introduced after source milestone 0.1.7.

## Goals

NOVA's distributed-systems learning and runtime environment is intentionally constrained to one Windows laptop. Docker Compose provides isolated service processes and a private virtual network; no cloud account, remote machine, Kubernetes cluster, or public endpoint is required.

The first increment introduces NATS JetStream and a containerized event observer while retaining the current Windows API, desktop, SQLite memory, scheduler, and native Windows integrations. The installed desktop starts the Compose services in a background supervisor, launches Docker Desktop when its standard Windows installation is detected, and stops only the Compose project it started when NOVA is quit.

## Current topology

```text
Windows laptop
  NOVA PySide6 desktop
       |
       | HTTP loopback
       v
  NOVA FastAPI host process
       |
       | NATS client (127.0.0.1:4222; opt-in)
       v
  Docker Compose private network
       |
       +---- NATS JetStream broker
       |       persistent stream: NOVA_EVENTS
       |
       +---- event-worker container
               durable observer: nova-event-observer
```

Only the broker's client and monitoring ports are published, and both bind to loopback. The event worker is not published to the host. Its container runs as an unprivileged user with a read-only root filesystem, dropped Linux capabilities, and no-new-privileges.

## Event contract

Every event uses a versioned JSON envelope:

- schema_version: event schema version (currently 1).
- event_id: unique UUID for correlation and deduplication.
- event_type: subject beginning with nova.events.
- occurred_at: UTC ISO-8601 timestamp.
- source: originating NOVA node identifier.
- payload: event-specific JSON object.

The first host events are nova.events.service.started and nova.events.service.stopping. The diagnostics endpoint emits nova.events.diagnostic. JetStream stores events for up to seven days in the named Docker volume. The observer uses a durable pull consumer and acknowledges messages after logging their metadata.

The observer is intentionally non-executing. It cannot launch applications, read files, invoke tools, or perform Windows automation. Future job workers must use separately defined schemas, typed allowlists, idempotency keys, bounded retries, and the existing NOVA approval model.

## Start and verify (installed desktop)

Requirements: Windows 10/11 and Docker Desktop with the Compose plugin. Install Docker Desktop once and complete its first-run setup. NOVA then starts Docker Desktop and its local Compose services when the desktop launches. The first container build downloads the base image and the small Python messaging dependency, so it requires an internet connection. No cloud account is used.

If Docker Desktop is missing or unavailable, NOVA continues to work in standalone mode and records the cluster startup issue in %APPDATA%\\NOVA\\logs\\cluster.log.

## Start and verify (developer checkout)

Requirements: Windows 10/11, Docker Desktop with the Compose plugin, and the NOVA development environment.

From PowerShell at the repository root:

```powershell
docker compose up -d --build
```

Enable messaging for the host API process in that PowerShell session:

```powershell
$env:NOVA_DISTRIBUTED_ENABLED = "true"
$env:NOVA_NATS_URL = "nats://127.0.0.1:4222"
$env:NOVA_NODE_ID = "nova-windows-host"
nova-service
```

In another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/cluster/status
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/cluster/diagnostics/publish -ContentType "application/json" -Body '{"message":"hello from the NOVA host"}'
docker compose logs -f event-worker
```

Expected status includes enabled: true, connected: true, and transport: nats-jetstream. The observer should log the diagnostic event ID and source.

Stop the services:

```powershell
docker compose down
```

The nova_nats_data volume persists between restarts. To intentionally erase broker history, use docker compose down -v; this does not delete NOVA's existing SQLite memory database.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| NOVA_DISTRIBUTED_ENABLED | true | Enable automatic local cluster management |
| NOVA_NATS_URL | nats://127.0.0.1:4222 | Local broker address |
| NOVA_NODE_ID | nova-windows-host | Host event source identity |

If NATS is unavailable at startup, NOVA retries in the background and continues in standalone mode until the broker is reachable. Messaging must not prevent local chat or Windows functionality from starting.

## Next increments

1. Validate this broker/observer slice on Windows and in CI.
2. Add an app-managed cluster supervisor so the installed desktop can start and stop Compose services without a terminal.
3. Add event publication for chat, memory, scheduler, and automation lifecycle boundaries.
4. Extract independent AI and memory service APIs while preserving SQLite data and migration compatibility.
5. Introduce typed durable job queues, replicated workers, idempotency, bounded retry/backoff, and dead-letter handling.
6. Add a Windows Host Agent boundary for native OS capabilities; containers must never receive unrestricted host access.
7. Add service health, dependency readiness, OpenTelemetry traces, and local dashboards.
8. Explore leader election and multi-replica scheduler coordination only after persistence and failure semantics are tested.

## Important boundaries

This is a distributed application running on one physical machine, not machine-level high availability. A laptop shutdown, disk failure, Docker engine failure, or Windows failure affects every local node. Containers provide process and dependency isolation, not a second physical fault domain.

Do not bind NATS to a LAN interface or expose the NOVA API publicly. Remote access requires a separate authentication, authorization, encryption, and threat-model review.