# NOVA architecture

## Runtime

NOVA uses a local FastAPI process bound to `127.0.0.1` by default. The optional PySide6 desktop client communicates with that process over loopback HTTP. The UI does not call the model runtime directly; model access remains behind the backend provider interface.

## Desktop client

- Entry point: `nova-desktop` (module: `nova.desktop`).
- Optional dependency group: `desktop` installs PySide6.
- The desktop client uses a worker thread for HTTP requests so model inference does not freeze the UI.
- The animated identity visual is drawn with Qt primitives to avoid external assets and keep GPU requirements modest.
- The backend persists conversation turns in SQLite; the desktop assigns a stable conversation ID for each chat session.
- The backend retrieves relevant approved memories and adds them as bounded context to chat requests.
- The desktop remains a thin client; memory management is exposed through typed API endpoints.
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

The SQLite memory service sits beside the provider adapter and is independent of model vendor/runtime.

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
5. SQLite conversation history and local vector memory with approval, editing, and deletion controls.
6. Permission manager, tool registry, and audit log.
7. Streaming text conversation.
8. Voice pipeline and small, allowlisted Windows tools.


## Streaming and request performance

- The backend reuses one provider instance and asynchronous HTTPX connection pool, closed during FastAPI shutdown.
- `POST /chat/stream` emits token events followed by `ttft_ms` and `total_ms`; `POST /chat` remains supported.
- Keeping model weights resident is a model-runtime setting. There is no universal keep-alive parameter across OpenAI-compatible servers.


## Persistent memory

The memory service is implemented in `src/nova/core/memory/store.py`. It uses the Python standard-library SQLite driver and stores conversations, messages, memory records, and normalized 256-dimensional feature-hash vectors. Retrieval ranks approved memories by cosine similarity locally. The deterministic encoder avoids a network dependency, external embedding service, model download, and GPU requirement; it is intentionally a lightweight first vector-retrieval implementation rather than a transformer embedding model.

Memory capture uses a hybrid policy: explicit remember requests and recognized low-risk preferences/projects are stored automatically; selected high-impact statements are queued as pending; sensitive credential and personal-identifier patterns are rejected. The API exposes approval, edit, and delete operations. Memory is inserted as contextual data, never as executable instructions.
