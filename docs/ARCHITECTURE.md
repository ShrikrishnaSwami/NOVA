# NOVA architecture

## Runtime

NOVA uses a local FastAPI process bound to `127.0.0.1` by default. The optional PySide6 desktop client communicates with that process over loopback HTTP. The UI does not call the model runtime directly; model access remains behind the backend provider interface.

## Desktop client

- Entry point: `nova-desktop` (module: `nova.desktop`).
- Optional dependency group: `desktop` installs PySide6.
- The desktop client uses a worker thread for HTTP requests so model inference does not freeze the UI.
- The animated identity visual is drawn with Qt primitives to avoid external assets and keep GPU requirements modest.
- The UI stores conversation history in memory for the current desktop session only. Durable memory is a separate future service.
- The backend URL can be overridden with `NOVA_API_URL`.

## AI provider layer

NOVA defines a provider contract in `src/nova/core/ai/types.py`. Provider implementations live behind that contract, so conversation orchestration does not depend on a particular model vendor or runtime.

The current adapters are:

- `echo`: safe setup mode that lets a fresh installation exercise the chat API without credentials.
- `openai_compatible`: adapter for local model servers and compatible hosted APIs using the chat-completions request format. It can connect to a local runtime such as Bionic, LM Studio, or llama.cpp server, or a compatible cloud endpoint.

Provider selection is controlled by environment variables. No API key is required for local endpoints that do not use authentication. Credentials belong in the local `.env` file and must never be committed.

## Request flow

```text
PySide6 desktop UI
       |
       v
Local FastAPI API (loopback)
       |
       v
Conversation endpoint
       |
       v
Provider adapter
       |
       v
Bionic / local model runtime
```

Planned services will add memory and permission-scoped tools beside the provider adapter.

## Trust boundaries

- Model responses are untrusted input, not executable instructions.
- The chat endpoint accepts only user/assistant history from clients; clients cannot inject system-role messages.
- Tools expose narrow, typed operations rather than arbitrary system access.
- Every tool has a declared risk level and permission policy.
- User approval is checked by application code, never inferred from model text.
- Secrets are read from local environment configuration and are never stored in source control.
- The local API must remain loopback-only unless an authenticated network mode is explicitly designed.

## Development milestones

1. API and configuration foundation.
2. Provider contract, setup-mode chat, and OpenAI-compatible adapter.
3. Local model runtime integration.
4. First desktop UI with threaded API requests.
5. SQLite memory with explicit retention and deletion controls.
6. Permission manager, tool registry, and audit log.
7. Streaming text conversation.
8. Voice pipeline and small, allowlisted Windows tools.
