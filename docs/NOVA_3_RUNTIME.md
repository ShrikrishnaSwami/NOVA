# NOVA 3.0 Runtime Architecture

This document describes the first runtime foundation milestone. It is deliberately
incremental: existing FastAPI, PySide6, local model, memory, voice, task scheduler,
and permissioned Windows controls remain in place.

## Runtime services

- `SystemStateMonitor` runs as an asyncio background task in the FastAPI lifespan.
- Telemetry sampling is offloaded with `asyncio.to_thread` so process inspection
  does not block the API event loop.
- The monitor records CPU, RAM commitment, network byte counters and throughput,
  foreground-window title (Windows), process count, and the top eight processes
  by resident memory.
- A bounded alert history reports sustained high CPU or memory use. Alerts are
  rate-limited and observational only; the monitor does not kill processes,
  change power settings, or run maintenance autonomously.

## Persona

The chat endpoint prepends a single system identity prompt. It sets concise,
composed British-style language and prohibits false claims about simulated or
physical actions. Existing retrieved memories remain separate context and never
override system policy.

## Tool runtime

- Tools have explicit names, descriptions, JSON-like argument schemas, and
  registered handlers.
- A chain is limited to five calls and is fully validated before the first call.
- Execution requires an explicit `approved: true` request.
- No shell, eval, generated Python, arbitrary file writes, or arbitrary process
  execution is exposed by this registry.
- Aerospace, smart-grid, thermal, and holographic subsystems are in-memory
  simulations. Every result is labelled `SIMULATION ONLY`.

## API

- `GET /runtime/state` — latest telemetry and recent alerts.
- `GET /runtime/tools` — registered tool descriptions.
- `POST /runtime/tools/execute` — bounded, approved tool chain.

## Next integration milestones

1. Connect runtime state to the PySide6 command-centre UI.
2. Add persistent, user-configurable alert policies and notification controls.
3. Add interruptible async voice sessions and wake-word support.
4. Add opt-in screen capture/OCR with a visible capture indicator and local
   processing by default.
5. Add model-compatible function calling only when the configured provider
   advertises and passes a capability check.
6. Add additional Windows actions as typed, individually permissioned tools.

The runtime currently supplies an API-level tool registry; it does not yet let
the LLM autonomously execute tool chains. That integration must preserve the
approval and validation rules above.
