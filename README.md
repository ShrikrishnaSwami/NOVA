# NOVA

**NOVA is an open-source, Windows-first desktop AI assistant.** It combines a desktop interface, voice interaction, local persistent memory, conversation history, scheduled read-only tasks, system awareness, and permission-gated Windows controls.

The project is under active development. The current source milestone is **0.1.7**. The Windows installer is built by GitHub Actions; check the workflow before treating a particular build as downloadable.

- Repository: https://github.com/ShrikrishnaSwami/NOVA
- Windows installer workflow: [Actions](https://github.com/ShrikrishnaSwami/NOVA/actions/workflows/windows-installer.yml)
- Documentation: [docs/](docs/)

## What NOVA can do today

### Desktop and lifecycle
- Runs as a Windows desktop application built with PySide6.
- The desktop starts and manages its own loopback-only API backend when needed. You do not need to open a terminal or manually start the backend when using the installed app.
- Supports a notification-area/tray lifecycle, optional Windows sign-in startup, a global `Ctrl+Alt+Space` shortcut, and single-instance protection.
- Stores user settings and memory separately from the application install directory so upgrades can preserve them.
- Closing the main window hides NOVA; use **Quit NOVA** from the tray menu to exit.

### AI chat and tools
- Supports an echo setup mode and an OpenAI-compatible chat-completions provider.
- Can connect to local model servers and compatible hosted endpoints.
- Supports streamed chat responses and bounded conversation context.
- The model can propose registered tools. NOVA validates proposals, shows the requested actions and arguments, and requires explicit approval before execution.
- Tool results—including failures and skipped steps—are returned to the model so it can explain what actually happened.
- Tool chains are capped at five calls and stop after the first failed step.

### Voice
- Offline speech recognition through Vosk.
- Optional local “Hey NOVA” wake-word listening.
- Push-to-talk remains available.
- Local speech output through Windows voices using pyttsx3.
- Active speech playback can be interrupted.
- Wake-word listening is opt-in and can be disabled. Microphone audio is processed locally; NOVA does not upload it to a cloud speech service.

### Memory and conversations
- Conversations and long-term memories are stored in a local SQLite database.
- Memory retrieval uses local feature-hash vectors and hybrid semantic/lexical ranking; no hosted embedding API or separate vector database is required.
- Memories can be reviewed, approved, edited, deleted, searched, and pinned.
- The desktop memory manager displays memory totals, pinned count, and retrieval usage.
- Conversation history can be searched by title and message contents, opened/resumed, renamed, pinned, and deleted.
- Pinned memories and conversations are prioritised in their respective lists.

### Windows awareness and controls
- Read-only system overview, process inventory, visible-window inventory, and foreground-window information.
- Discover and launch installed Windows applications.
- Search accessible local folders and supported text/document files.
- Read or open selected local files after confirmation.
- Control supported visible windows: focus, minimize, restore, maximize, and request a graceful close.
- Adjust supported master volume and internal display brightness, and open native Windows Search.
- Use a limited set of Windows UI Automation actions on accessible controls, with explicit approval.
- Optional battery and active-window awareness while the Computer Controls panel is open.

### Scheduled tasks and alerts
- Persistent local scheduler with one-time, daily, and weekly recurrence.
- Jobs require approval before they can run.
- Current scheduled actions are read-only system and storage reports.
- Tasks can be listed, paused, cancelled, and inspected through execution history.
- Optional native Windows notifications can report NOVA replies, task outcomes, and system alerts.

## Local distributed runtime (experimental foundation)

NOVA now includes a laptop-only distributed runtime foundation that the installed desktop manages automatically when Docker Desktop is available:

- Docker Compose runs a local NATS JetStream broker and a separate event-observer worker.
- Broker ports bind to 127.0.0.1 only; the worker communicates over a private Compose network.
- JetStream persists versioned events in a Docker volume for up to seven days.
- The Windows-hosted NOVA API publishes lifecycle events to the broker and retries its connection in the background.
- GET /cluster/status reports the host-to-broker connection, and POST /cluster/diagnostics/publish sends a harmless test event.
- The cluster is enabled by default. NOVA can launch Docker Desktop if installed; if Docker is unavailable or its first-run setup is incomplete, NOVA continues in standalone mode.

This is the first infrastructure milestone, not yet a migration of chat, memory, scheduling, or Windows automation into separate services. SQLite remains the source of truth for existing conversations and memories. The Windows Host Agent boundary and service-by-service extraction are subsequent milestones.

### Start the local cluster for development

The installed desktop starts the local Compose cluster automatically and stops the services it started when you quit NOVA. Docker Desktop must be installed; the first Docker image build requires an internet connection. NOVA does not need a cloud account or remote server.

For a source checkout, install Docker Desktop, open PowerShell in the repository, then run:

```powershell
docker compose up -d --build
```

In the same PowerShell session, start the NOVA API with local messaging enabled (this is already the default configuration):

```powershell
$env:NOVA_DISTRIBUTED_ENABLED = "true"
$env:NOVA_NATS_URL = "nats://127.0.0.1:4222"
nova-service
```

Check http://127.0.0.1:8000/cluster/status, then publish a test event:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/cluster/diagnostics/publish -ContentType "application/json" -Body '{"message":"NOVA local event pipeline test"}'
docker compose logs -f event-worker
```

Stop the containers with `docker compose down`. Persistent broker data remains in the `nova_nats_data` volume; use `docker compose down -v` only if you intentionally want to erase it.

The containerized worker is currently an observer/diagnostic consumer. It does not execute computer-control actions. Production job queues, replicated task workers, and service extraction will be added in later milestones after this foundation is validated.

## What NOVA does not do

NOVA is not an unrestricted autonomous computer operator. It does not expose arbitrary shell commands, generated scripts, unrestricted Python execution, or arbitrary process termination. Model output is untrusted input. Registered actions are validated and permission-gated; physical actions require user confirmation.

Some subsystems are simulations, not hardware integrations. In particular, the aerospace, smart-grid, thermal, and holographic examples in the runtime tool registry are labelled simulations and do not control physical devices.

NOVA does not read notifications generated by other Windows applications. It does not silently capture the screen or camera. Gesture control is a design document only and is not currently implemented.

## Install NOVA on Windows

The easiest way to use NOVA is the packaged Windows installer.

1. Open the [NOVA Windows installer workflow](https://github.com/ShrikrishnaSwami/NOVA/actions/workflows/windows-installer.yml).
2. Select the latest successful run for the version you want.
3. Scroll to **Artifacts** and download **NOVA-Windows-Installer**.
4. Extract the downloaded ZIP.
5. Run the included `NOVA-Setup-<version>.exe`.
6. Launch NOVA from the Start Menu or desktop shortcut.

The artifact is a ZIP containing the installer executable. The installer is per-user and does not require administrator privileges. The workflow also creates **NOVA-Portable-Windows**, which contains the complete portable application folder. Extract the entire folder and run `NOVA\NOVA.exe`; do not move the executable out of its bundled folder.

A successful workflow run is required before its artifacts are available. Do not use an in-progress or failed run as an installer source.

## First-time setup

1. Launch NOVA.
2. Open **NOVA settings** from the desktop or tray menu.
3. Configure the AI provider and model endpoint in the settings file if you want model-backed responses.
4. Start your selected local model runtime, if using a local model.
5. Return to NOVA and test a text conversation.
6. Optionally configure your microphone, test it, and enable **Hey NOVA**.
7. Review notification, sign-in startup, and microphone preferences before enabling them.

A fresh install can run in echo/setup mode without model credentials. For useful AI responses, configure a model provider.

### Local model configuration

NOVA uses an OpenAI-compatible chat-completions interface. Example configuration for a local server:

```dotenv
NOVA_AI_PROVIDER=openai_compatible
NOVA_AI_MODEL=your-model-id
NOVA_AI_BASE_URL=http://127.0.0.1:1234/v1
NOVA_AI_API_KEY=
NOVA_AI_TIMEOUT_SECONDS=120
```

Use the exact model ID and URL shown by your runtime. NOVA does not bundle a large language model. Local model performance depends on the runtime, model size, quantization, and available CPU/GPU acceleration.

The initial template may contain a Bionic-compatible example endpoint. If you use another runtime, replace it with that runtime's actual endpoint. Keep API keys and other secrets in the private user configuration file; never commit them.

## Voice setup

The packaged Windows application includes the small English Vosk model. Open NOVA settings to select a microphone and run a test. Enable **Hey NOVA** only when you want continuous local wake-word listening. Push-to-talk is available as an alternative.

See [Local voice setup](docs/VOICE_SETUP.md) for the complete explanation and troubleshooting steps.

## Memory and conversation usage

### Memory manager
Open **NOVA Memory** from the desktop interface.

- Search by memory content or category.
- Review pending suggestions and approve them when appropriate.
- Edit or delete a selected memory.
- Pin important memories or unpin them.
- See total memories, pinned memories, and retrieval counts.
- Pinned memories are prioritised during retrieval.

NOVA avoids storing credentials and other secret-like content. Some sensitive personal facts are held for review rather than automatically used. Memory is stored locally in SQLite.

### Conversation history
Open **Conversation history** from the desktop.

- Search across conversation titles and message contents.
- Open a conversation to resume it.
- Rename a conversation.
- Pin or unpin it; pinned conversations appear first.
- Delete a conversation and its messages after confirmation.

### Local data locations

On Windows, the installed app uses:

- Settings: `%APPDATA%\NOVA\.env`
- Preferences: `%APPDATA%\NOVA\preferences.json`
- SQLite database: `%LOCALAPPDATA%\NOVA\nova_memory.sqlite3`
- Installed application: `%LOCALAPPDATA%\Programs\NOVA`

Upgrades are designed to preserve the settings and SQLite database. Back up the database and settings file before manually changing or removing user data.

## Computer controls

Open **Computer controls** in the desktop interface. The available actions depend on Windows support and optional dependencies.

- Application discovery and launch use the Windows application catalogue.
- File operations are scoped to configured or discovered local roots and the current Windows user's access.
- Read, open, list, and other consequential operations require confirmation.
- Window actions are limited to a selected visible window and require confirmation. Close sends a normal Windows close request; the target application may show a save prompt.
- UI Automation can activate supported accessible controls or enter text into a uniquely identified non-password field. It cannot operate reliably on applications that expose no accessibility information.
- System volume and brightness controls depend on the hardware and optional Windows integrations.

The default local drive discovery is not a promise that NOVA can bypass Windows access controls. Protected folders remain subject to the signed-in account's permissions. See [Architecture](docs/ARCHITECTURE.md) for the boundaries and [security model](docs/WINDOWS_INSTALLER.md).

## Scheduled tasks

The scheduler currently supports read-only system and storage reports. Create a task, inspect its details, and explicitly approve it before it can run. Supported recurrence options are once, daily, and weekly. Tasks can be paused or cancelled and have local execution history.

See [Task scheduler](docs/TASK_SCHEDULER.md) for API routes and examples.

## API and developer information

The local backend defaults to `http://127.0.0.1:8000`:

- `GET /health` — health check.
- `GET /docs` — interactive API documentation.
- `POST /chat` and `POST /chat/stream` — chat.
- `GET /system/ai` — configured AI provider status.
- `GET /memory`, `GET /memory/stats`, `GET /memory/search` — memory.
- `GET /conversations`, `GET /conversations/search` — conversation history.
- `GET /tasks` and `GET /tasks/capabilities` — scheduler.
- `GET /runtime/state` and `GET /runtime/tools` — runtime telemetry and registered tools.
- `GET /cluster/status` — optional local distributed-runtime status.
- `POST /cluster/diagnostics/publish` — publish a harmless diagnostic event when messaging is enabled.
- `GET /computer/automation/capabilities` — supported automation action contracts.

The installed application starts and manages the backend itself. You do not need these endpoints for ordinary desktop usage.

### Development checkout

For contributors working from source, use Windows 10/11 and Python 3.11 or newer. Python 3.13 is supported by the current CI matrix.

```powershell
git clone https://github.com/ShrikrishnaSwami/NOVA.git
cd NOVA
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,desktop,voice,windows,documents]"
Copy-Item .env.example .env
pytest
```

Run the desktop during development with:

```powershell
nova-desktop
```

Run the backend separately only when you are developing or testing the API:

```powershell
uvicorn nova.main:app --reload
```

The installed desktop application does not require this manual development workflow.

## Documentation

- [Architecture and implementation boundaries](docs/ARCHITECTURE.md)\n- [Local distributed runtime](docs/DISTRIBUTED_RUNTIME.md)
- [Windows installer and lifecycle](docs/WINDOWS_INSTALLER.md)
- [Local voice setup](docs/VOICE_SETUP.md)
- [Memory, tools, and voice internals](docs/MODEL_TOOLS_AND_VOICE.md)
- [Scheduled tasks](docs/TASK_SCHEDULER.md)
- [Runtime architecture](docs/NOVA_3_RUNTIME.md)
- [Local model benchmarking](docs/LOCAL_MODEL_BENCHMARK.md)
- [Gesture control design (not implemented)](docs/GESTURE_CONTROL.md)

## Roadmap

The next milestones focus on improving proactive assistance, reliable reminder workflows, desktop lifecycle and status visibility, broader user-facing management, and continued Windows end-to-end testing. Planned features are not current capabilities until implemented, tested, and included in a successful build.

## License

MIT. See [LICENSE](LICENSE).
