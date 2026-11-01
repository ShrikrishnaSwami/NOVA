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
- Optional voice input runs Vosk in a worker thread and reads audio only after the user clicks Talk; optional speech output uses local Windows SAPI voices through pyttsx3.
- Voice dependencies are isolated in the `voice` extra, and the Vosk model is downloaded separately and configured with `NOVA_VOSK_MODEL_PATH`.
- The Computer controls dialog exposes a fixed allowlist of Windows applications and file operations limited to configured roots.

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
6. Permission manager, tool registry, and audit log (first implementation now available).
7. Streaming text conversation.
8. Voice pipeline foundation: local push-to-talk transcription and local speech output. Next: user-approved file handoff to chat and carefully scoped natural-language tool planning.


## Streaming and request performance

- The backend reuses one provider instance and asynchronous HTTPX connection pool, closed during FastAPI shutdown.
- `POST /chat/stream` emits token events followed by `ttft_ms` and `total_ms`; `POST /chat` remains supported.
- The desktop batches incoming stream fragments into short UI updates instead of repainting and scrolling for every fragment.
- `NOVA_AI_MAX_TOKENS` bounds response generation (default 512); raise it for longer answers.
- `NOVA_AI_CONTEXT_MESSAGES` bounds previous conversation context (default 8 messages; maximum 20).
- For model IDs containing `qwen3`, `NOVA_AI_QWEN_NO_THINK=true` adds Qwen's documented `/no_think` prompt switch. A user can request reasoning for an individual turn with `/think`.
- `NOVA_AI_TOP_P` defaults to 0.8, matching Qwen3's recommended non-thinking sampling settings.
- Keeping model weights resident is a model-runtime setting. There is no universal keep-alive parameter across OpenAI-compatible servers; configure Bionic's model unloading/residency setting if available.
- These controls reduce prompt and output work but cannot overcome the CPU throughput limit of a small local machine.


## Persistent memory

The memory service is implemented in `src/nova/core/memory/store.py`. It uses the Python standard-library SQLite driver and stores conversations, messages, memory records, and normalized 256-dimensional feature-hash vectors. Retrieval ranks approved memories by cosine similarity locally. The deterministic encoder avoids a network dependency, external embedding service, model download, and GPU requirement; it is intentionally a lightweight first vector-retrieval implementation rather than a transformer embedding model.

Memory capture uses a hybrid policy: explicit remember requests and recognized low-risk preferences/projects are stored automatically; selected high-impact statements are queued as pending; credentials, financial secrets, and government identifiers are rejected; detected sensitive personal facts are queued for user approval. The API exposes approval, edit, and delete operations. Memory is inserted as contextual data, never as executable instructions.


## Computer control and permission model

The initial computer-control registry lives in `src/nova/core/computer/registry.py`; its API is in `src/nova/api/computer.py`, and the desktop approval surface is `src/nova/desktop_computer.py`.

- Applications are selected from a fixed allowlist (Notepad, Calculator, Paint, File Explorer); no user/model-supplied executable path is accepted.
- File operations are disabled unless `NOVA_COMPUTER_ALLOWED_ROOTS` contains one or more existing folders separated by semicolons.
- Directory listing, filename search, and text-file reading resolve paths and verify they remain under an approved root. Symlink escapes are rejected.
- Text reads are limited to a small extension allowlist and 64 KB; filename search is capped at 200 results.
- The desktop asks for confirmation for each action and defaults the dialog to No. The API rejects requests without an explicit approval flag.
- Action metadata is stored in the existing local SQLite database in a `computer_audit` table. File contents are not logged.
- The language model cannot call this API automatically. A future milestone may add intent planning, but it must preserve this approval boundary.

This is a local-user permission boundary, not a hardened multi-user security boundary. Keep the API bound to loopback; do not expose it to a network without adding authentication and a stronger authorization design.
