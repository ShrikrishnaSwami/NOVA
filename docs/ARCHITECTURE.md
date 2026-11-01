# NOVA architecture

This document describes the implementation represented by the current `main` branch (source milestone 0.1.7). It distinguishes shipped behaviour from future ideas; a roadmap item is not a capability until code and tests exist.

## High-level design

NOVA is split into a Windows desktop client, a local API/backend, provider adapters, and local persistence.

```text
PySide6 desktop application
  |  chat, history, memory, settings, approvals, voice, tray
  v
Loopback FastAPI service (127.0.0.1)
  |-- chat orchestration and provider interface
  |-- tool registry and typed Windows APIs
  |-- task scheduler and system-state monitor
  |-- SQLite conversation and memory store
  v
Configured OpenAI-compatible model endpoint
  (local model runtime or compatible hosted service)
```

The desktop is the user-facing application. It manages a backend child process when no healthy local API is already running. The backend is bound to loopback by default; it is not intended to be exposed as an unauthenticated network service.

## Windows desktop and lifecycle

- Desktop entry point: `nova-desktop` / `nova.desktop`.
- UI framework: PySide6.
- The desktop uses worker threads for operations that would otherwise block the UI.
- The installed application is packaged with PyInstaller and distributed through a per-user Inno Setup installer.
- It can minimise to the Windows notification area, optionally start at sign-in, and reopen through `Ctrl+Alt+Space`.
- A single-instance lock prevents multiple desktop sessions for the same user profile.
- Closing the main window hides it; **Quit NOVA** exits the desktop and the API child process it owns.
- It does not stop an API process that it did not start.
- The installed app runs in the interactive signed-in user's session, not as LocalSystem.

The packaged application is self-starting: users launch the shortcut or executable. Starting a terminal, manually launching Uvicorn, or entering source commands is a development-only workflow.

## AI provider and chat flow

The provider contract is defined under `src/nova/core/ai`. Current modes include:

- `echo`: setup/testing mode that does not require model credentials.
- `openai_compatible`: OpenAI-compatible chat-completions API adapter. It can connect to a local inference server or a compatible hosted endpoint.

NOVA does not bundle a foundation model. Model selection, model weights, inference speed, and residency are controlled by the configured runtime/provider.

Chat requests are handled by the backend. It applies the assistant system policy, bounded conversation context, and relevant approved memories before calling the provider. Streaming is available through `POST /chat/stream`; the ordinary `POST /chat` endpoint remains available.

## Tool planning, validation, and approval

The runtime agent can ask the configured model to propose tool calls. Proposals are not authority to act.

1. The model returns a structured proposal.
2. NOVA validates tool names and arguments against the registered schema.
3. The desktop shows the proposed action and its arguments.
4. The user approves or denies the operation.
5. The backend executes only the registered handler after approval.
6. Actual results, including failures, are returned to the model for explanation.

Chains are limited to five calls and validated in full before the first handler runs. Execution stops after the first failed step; later steps are marked skipped. Unknown tools, malformed arguments, and unregistered actions fail closed.

The registry includes read-only system and visible-window information, plus explicitly labelled simulation-only subsystem tools. Mutating Windows operations use separate typed endpoints and confirmation flows. NOVA does not expose arbitrary shell, eval, generated Python, or unrestricted process execution.

## Windows computer integration

The computer integration is split between `src/nova/core/computer`, API routes under `src/nova/api`, and desktop approval UI.

Implemented capabilities include:

- Discovering installed applications and launching a selected match through Windows mechanisms.
- Discovering or configuring accessible local roots; Windows permissions still apply.
- Listing directories and searching supported filenames and document contents.
- Reading or opening selected files with confirmation.
- Read-only system, process, and visible-window inspection.
- Focus, minimize, restore, maximize, and graceful close of a selected visible window.
- Typed volume, supported brightness, and native Windows Search actions.
- A limited Windows UI Automation adapter for supported accessible controls.
- Optional battery and foreground-window awareness while the relevant panel is open.
- A local audit trail for supported computer actions.

A graceful close sends the normal Windows close message. It does not force-terminate an application; the application can prompt the user to save work.

File search and reading are bounded. Inaccessible locations are skipped or rejected. The implementation does not bypass Windows ACLs, follow arbitrary links during recursive search, or promise OCR/semantic indexing for every file type. Document extraction depends on optional local libraries.

UI Automation is constrained to enumerated visible controls. It is not arbitrary keyboard injection or a guarantee that every application's controls are accessible.

## Voice pipeline

- Speech capture: `sounddevice` / PortAudio.
- Offline recognition and wake phrase: Vosk.
- Speech output: pyttsx3 using installed Windows voices.
- The packaged Windows build includes the small English Vosk model.
- Wake-word mode is opt-in; push-to-talk is available.
- The desktop can interrupt current speech output when a wake-word interaction begins.
- Microphone selection and test controls are exposed in desktop settings.

Audio processing is local to the device. NOVA does not upload microphone audio to a cloud speech API.

## Persistent storage and memory

The local SQLite store contains conversation records, messages, long-term memories, retrieval metadata, and related local state.

Memory capabilities include:

- Explicit remember requests and selected low-risk automatic captures.
- Pending review for selected sensitive or high-impact suggestions.
- Rejection of credential-like content.
- Local feature-hash vector representation and cosine similarity retrieval.
- Hybrid semantic/lexical ranking.
- Pinned-memory prioritisation.
- Duplicate and near-duplicate prevention.
- Access counts and last-access timestamps.
- Search, list, approve, edit, pin, and delete operations.

This is a lightweight local retrieval system, not a transformer embedding service. It does not require a hosted embedding endpoint or separate vector database. Memory content is contextual data, not executable instructions.

Conversation history supports search across title and message text, open/resume, rename, pin/unpin, and delete. The pin column is added through an additive SQLite migration so existing databases can be upgraded without discarding prior records.

## Scheduler and system monitoring

The scheduler persists jobs and execution history in SQLite. Current scheduled handlers are read-only system and storage reports. Jobs begin pending approval; supported recurrence includes once, daily, and weekly. Users can approve, pause, cancel, and inspect history.

The system-state monitor collects bounded local telemetry and can emit rate-limited alerts for sustained resource conditions. It is observational: it does not kill processes or silently modify system settings.

Native Windows notifications are optional and user-controlled. NOVA can display its own notifications but does not read notifications from other applications.

## Data locations on Windows

- User settings: `%APPDATA%\NOVA\.env`
- User preferences: `%APPDATA%\NOVA\preferences.json`
- Local database: `%LOCALAPPDATA%\NOVA\nova_memory.sqlite3`
- Installed program: `%LOCALAPPDATA%\Programs\NOVA`

The installer keeps user data outside the application directory and is designed to preserve settings and SQLite data during upgrades.

## Security and trust boundaries

- Keep the local API bound to loopback.
- Store credentials in private per-user configuration; do not commit them.
- Model output is untrusted and must pass schema validation.
- Tool execution requires explicit user approval.
- Each tool has a finite contract; no arbitrary shell or generated-code execution is exposed.
- Computer actions are scoped, confirmed, and audited where applicable.
- The app runs with the signed-in user's permissions and does not request administrator elevation as part of normal operation.
- Simulation results are labelled and must never be represented as physical actions.
- The application does not silently capture screen, camera, or third-party notification content.

This is a single-user local desktop architecture, not a hardened multi-user remote service. Do not expose the API to a LAN or public network without authentication, authorization, and a separate threat review.

## Development and testing

Install the development extras on Windows:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,desktop,voice,windows,documents]"
pytest
```

The GitHub Actions workflows run automated tests and package the Windows application. The installed application is the intended end-user path; manual Python commands are for contributors.
