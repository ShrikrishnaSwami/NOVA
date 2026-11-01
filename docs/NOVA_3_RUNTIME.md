# NOVA runtime architecture

This document describes the runtime services currently present in NOVA. The “NOVA 3.0” title refers to a longer-term architecture direction, not a claim that the product has reached a 3.0 release.

## Runtime services

The FastAPI application owns the backend lifespan. Runtime services are started and stopped with that application.

### System state monitor

- Samples local CPU, memory, network, foreground-window, and process information.
- Uses background/thread offloading for operations that should not block the API event loop.
- Keeps bounded recent telemetry and alert history.
- Can report sustained high CPU or memory conditions.
- Alerts are rate-limited and observational only.
- It does not kill processes, modify power settings, or perform unapproved maintenance.

The monitor runs locally. Telemetry is not a remote monitoring service.

## Assistant persona and chat

The chat endpoint applies a system identity and safety policy before calling the configured provider. Retrieved memories are supplied as bounded context and cannot override system policy.

The provider layer supports echo/setup mode and an OpenAI-compatible chat-completions adapter. NOVA does not bundle a foundation model; model inference occurs in the configured local runtime or compatible hosted service.

## Tool runtime

- Tools have explicit names, descriptions, argument schemas, and registered handlers.
- Chains are limited to five calls.
- The entire chain is validated before execution.
- Execution requires explicit approval.
- Failed steps stop the chain and later steps are skipped.
- Partial results are preserved for accurate explanation.
- No arbitrary shell, eval, generated Python, arbitrary file writes, or arbitrary process execution is exposed through the model tool registry.
- Simulation-only tools are labelled and do not operate physical hardware.

The desktop displays a confirmation surface before the registered tool chain is executed. Model-generated content is never treated as executable authority.

## API surface

- `GET /runtime/state` — latest system telemetry and recent alerts.
- `GET /runtime/tools` — registered tool descriptions.
- `POST /runtime/tools/plan` — propose a structured tool chain.
- `POST /runtime/tools/execute` — execute an approved, validated chain.

Other API routers provide chat, conversations, memory, tasks, and Windows computer operations.

## Implemented integrations

The runtime is integrated with the desktop's model-guided tool approval flow, local SQLite memory, the scheduler, system-state alerts, optional Windows notifications, and the typed Computer Controls APIs.

The desktop also supports local wake-word voice sessions, push-to-talk, and interruptible speech playback. These are implemented user-facing features, not merely API stubs.

## Future work

Potential future work includes more persistent user-configurable alert policies, richer status dashboards, opt-in local screen understanding, additional typed Windows actions, and provider capability negotiation. These are not claims about current functionality. Any future capture or automation feature must preserve visible controls, explicit consent, narrow permissions, and local processing where practical.
