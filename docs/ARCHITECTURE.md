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
- Computer controls discover Start Menu shortcuts, registered Windows Start Apps, classic uninstall registry entries, install locations, and App Paths. Direct app-launch requests are matched against the live catalogue; ambiguous matches are presented for user selection. Launching delegates to the Windows Shell and requires per-launch confirmation.
- When no explicit `NOVA_COMPUTER_ALLOWED_ROOTS` are configured, the backend discovers ready local drives and scopes file operations to paths the current Windows account can access. Search skips inaccessible directories, symbolic links, and junctions.
- Text and code files can be searched/read locally. The optional `documents` dependency group adds bounded extraction for PDF, DOCX, XLSX, and XLSM files. No document content is sent to the model unless a later, explicit chat workflow chooses to include it.

## Windows document extraction

`src/nova/core/computer/registry.py` routes document extraction by file extension. PDF uses `pypdf`, Word uses `python-docx`, and Excel uses `openpyxl`; these are optional, free, local dependencies installed with `pip install -e ".[documents]"`. Extraction is bounded by file size, page/sheet/row limits, and output character limits. Search results expose short previews; full document text is shown locally in the computer controls dialog. OCR, legacy binary `.doc`, and persistent Windows Search indexing are not yet implemented.

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

The Windows computer integration lives in `src/nova/core/computer/registry.py`; its API is in `src/nova/api/computer.py`, and the desktop approval surface is `src/nova/desktop_computer.py`.

- Application discovery combines current-user/all-users Start Menu shortcuts, the registered Windows Start Apps catalogue, classic uninstall registry entries, and App Paths. Executable launch is limited to paths discovered from those OS sources; packaged apps use their registered AppID.
- When `NOVA_COMPUTER_ALLOWED_ROOTS` is empty, NOVA discovers ready local drive roots and scopes operations to locations the current Windows account can actually access. Setting the variable explicitly narrows the scope to the listed folders.
- Directory listing, filename search, content search for supported text formats, text reading, and opening a path resolve targets and verify containment inside the discovered roots. Symlinks and junctions are not followed during recursive search.
- Text reading/content search supports a bounded set of text/code formats up to 2 MB per file; results are capped at 500. PDF/Office document extraction and a persistent Windows Search-backed index remain future work.
- The desktop asks for confirmation before opening or reading a selected item and defaults to No. Search is read-only. The API rejects mutating/open/read actions without an explicit approval flag.
- Action metadata is stored in the existing local SQLite database in a `computer_audit` table. File contents are not logged.
- The desktop currently has deterministic request routing for direct app launches. A broader natural-language planner that can choose among discovery, search, open, read, and Windows settings tools is the next milestone; model output must never become executable authority.

This is a local-user permission boundary, not a hardened multi-user security boundary. Keep the API bound to loopback; do not expose it to a network without adding authentication and a stronger authorization design.


## Natural-language computer planner

The first planner layer is deterministic and deliberately narrow. It recognizes filename searches, content searches, and explicit full-path open/read/list requests, then proposes typed actions to the desktop. It does not execute actions or treat model output as authority. The desktop shows a one-action confirmation before the API call; file contents remain local in the computer-controls panel. Filename search can scan all configured/accessibly discovered roots when no root is supplied. More conversational multi-step planning, Windows Search integration, OCR, and app/window automation remain later milestones.


## Windows OS awareness

The first OS-introspection module is `src/nova/core/computer/windows.py`. It provides a read-only system overview, bounded process inventory via psutil, and visible top-level/foreground window metadata via the Windows user32 API. Process command lines and environment variables are intentionally excluded. API endpoints are `GET /computer/system`, `GET /computer/processes`, and `GET /computer/windows`. The desktop can also control a selected visible window through `POST /computer/windows/actions`: focus/switch, minimize, restore, or maximize. Every operation requires an explicit one-action approval. Closing windows and synthesizing keyboard/mouse input are intentionally not exposed in this milestone. The API validates that the target is still a visible top-level window and never elevates privileges. A deterministic desktop intent parser recognizes `switch to`, `focus on`, `bring up`, `minimize`, `restore`, and `maximize` requests, resolves them against visible window titles, and routes them through the same confirmation surface. Ambiguous title matches are presented for user selection.


## Windows system controls, search, and opt-in events

src/nova/core/computer/system_controls.py contains fixed, typed Windows operations for master volume (via the optional pycaw Core Audio adapter), supported internal-display brightness (via the Windows WMI brightness methods), and launching a native search-ms query. The API endpoints are POST /computer/system/volume, POST /computer/system/brightness, and POST /computer/windows/search. Every mutation requires an explicit approval field and is written to the local computer audit log. There is no generic command or PowerShell endpoint. Brightness support varies by device; external monitors are commonly unsupported. Windows Search is opened in the native shell rather than scraped or queried outside its own index permissions.

A deterministic planner recognizes numeric volume/brightness requests and bounded Windows Search phrases. The desktop displays a confirmation before invoking the typed endpoint. The optional active-app watcher is user-started, polls only the foreground window title every two seconds while the Computer Controls dialog is open, and stops when the dialog closes. It does not persist titles, capture screen contents, or add window context to AI prompts. It is intentionally off by default.

The optional windows dependency group installs pycaw for master audio control. Core APIs remain importable without that optional package; attempting audio adjustment without it returns an actionable setup error.


## Application UI Automation boundary

The optional pywinauto adapter in src/nova/core/computer/ui_automation.py attaches to an existing visible top-level window by its enumerated HWND. It exposes only enabled, visible Button, TabItem, MenuItem, Hyperlink, CheckBox, and RadioButton controls with accessible names. Activation requires an exact name and control type that resolve to exactly one current control, plus explicit desktop/API approval. It does not send arbitrary text, read edit controls, execute scripts, or operate on unlisted windows. UI Automation availability depends on the target application's accessibility tree; some apps expose incomplete controls.
