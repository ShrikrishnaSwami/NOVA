# NOVA

NOVA is an open-source hybrid AI desktop assistant for Windows, built around voice, memory, local and cloud intelligence, and permission-based computer control.

The project is in active early development. The current release includes a local FastAPI backend, a provider-independent chat layer, and the first lightweight Windows desktop interface.

## Current capabilities

- Local FastAPI backend bound to `127.0.0.1`.
- Health endpoint at `/health`.
- Interactive API documentation at `/docs`.
- Chat endpoint at `/chat`.
- Provider status at `/system/ai`.
- Echo setup mode that works without model credentials.
- OpenAI-compatible adapter for local model servers and compatible hosted APIs.
- Optional PySide6 desktop client with animated NOVA visual, chat, and backend/model status.
- Optional local push-to-talk speech recognition and operating-system text-to-speech.
- SQLite-backed persistent conversations and user-controlled long-term memories.
- Local feature-hash vector similarity retrieval; no cloud embeddings or GPU required.
- Memory review, approval, editing, and deletion API.
- Permission-gated Windows integration that discovers installed applications and scans accessible local drives by default.
- Local audit log for completed or blocked computer operations.\n- Read-only Windows session awareness: OS and resource overview, running-process inventory, visible-window inventory, and foreground-window detection.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer (Python 3.13 is supported)
- Git

## Install

```powershell
git clone https://github.com/ShrikrishnaSwami/NOVA.git
cd NOVA

py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[dev,desktop]"

Copy-Item .env.example .env
```

If PowerShell blocks activation, run this in the same terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

## Configure a local model

NOVA connects to any server that implements the OpenAI-compatible chat-completions API. Start your local model server, then configure the local `.env` file:

```dotenv
NOVA_AI_PROVIDER=openai_compatible
NOVA_AI_MODEL=your-model-id
NOVA_AI_BASE_URL=http://127.0.0.1:1234/v1
NOVA_AI_API_KEY=
NOVA_AI_TIMEOUT_SECONDS=120
```

Use the exact model ID and API address shown by your model runtime. Keep `.env` private and never commit credentials.

## Run NOVA

Start the desktop interface:

```powershell
nova-desktop
```

NOVA checks whether its local API is already healthy. If not, it starts a backend process bound only to the configured loopback address and port, then connects the desktop automatically. When you choose **Quit NOVA**, it stops only the backend process that this desktop instance started; it never terminates a backend that was already running.

For development, you can still start the backend manually in a separate terminal:

```powershell
uvicorn nova.main:app --reload
```

The desktop client normally connects to `http://127.0.0.1:8000`. To use a different backend address, set `NOVA_API_URL` before launching it:

```powershell
$env:NOVA_API_URL = "http://127.0.0.1:8000"
nova-desktop
```

You can also use the backend without the desktop client:

- Health: http://127.0.0.1:8000/health
- API docs: http://127.0.0.1:8000/docs
- AI status: http://127.0.0.1:8000/system/ai

## Local voice (optional)

NOVA can transcribe microphone input locally with Vosk and read responses aloud using the installed Windows speech voices through pyttsx3. Voice input is push-to-talk; it does not continuously listen or use a wake word. Audio is processed on the device and is not sent to a cloud speech service. See [docs/VOICE_SETUP.md](docs/VOICE_SETUP.md) for installation and model setup. Install the optional dependencies with `pip install -e ".[desktop,voice,windows]"`.

## Persistent memory

NOVA stores its conversation history and long-term memories in a local SQLite database. By default the database is created at `~/.nova/nova_memory.sqlite3`; override it with `NOVA_MEMORY_DB_PATH` in your private `.env` file.

Memory retrieval uses deterministic local feature-hash vectors and cosine similarity. It does not send memory text to an embedding API and does not require a separate vector database. This is intentionally lightweight; a dedicated local embedding model can replace the encoder later.

Memory policy:
- Explicit `remember that ...` requests are saved.
- Safe preferences, interests, and project facts may be saved automatically.
- High-impact suggestions are marked pending until approved.
- Passwords, API keys, financial secrets, and government identifiers are never saved. Detected sensitive personal facts (such as health details or contact information) are held pending your approval.
- Memories can be listed, approved, edited, and deleted through the API.

Useful endpoints:
- `GET /memory` — list memories.
- `GET /memory?status=pending` — review suggestions.
- `POST /memory/{id}/approve` — approve a suggestion.
- `PATCH /memory/{id}` — edit a memory.
- `DELETE /memory/{id}` — delete a memory.
- `GET /conversations` and `GET /conversations/{id}` — browse saved conversations.
- `DELETE /conversations/{id}` — delete a conversation and its messages.

## Computer controls (Stage 4)

Open **Computer controls** in the desktop sidebar. The current OS-discovery foundation supports:

- Discover Windows Start Menu shortcuts, registered packaged apps, and classic installed desktop apps.
- Discover ready local drive roots automatically when `NOVA_COMPUTER_ALLOWED_ROOTS` is empty. This is the full-accessible-drive mode selected for NOVA; Windows still enforces the permissions of the signed-in account.
- Override automatic discovery with specific folders in the private `.env` file if you later want a narrower scope. Separate multiple paths with semicolons:

```dotenv
NOVA_COMPUTER_ALLOWED_ROOTS=C:\\Users\\YourName\\Documents;C:\\Users\\YourName\\Desktop
```

- Search file and folder names, search inside supported text/code and PDF/Word/Excel documents, list folders, read supported files up to 2 MB, and ask Windows to open a discovered path.
- Require a separate confirmation before opening or reading items. Search is read-only; inaccessible or protected locations are skipped by Windows permissions.
- Keep a local audit record of action type, safe parameters, outcome, and timestamp. File contents are never written to the audit log.

Text/code search supports TXT, Markdown, Python, JSON, CSV, LOG, YAML, TOML, INI, HTML, XML, SQL, JavaScript, TypeScript, CSS, Java, C/C++, PowerShell, batch, shell, and RTF. PDF, DOCX, XLSX and XLSM extraction is available through free local libraries. Install it with `pip install -e ".[documents]"`. PDF extraction is bounded to 100 pages; spreadsheets are bounded to 30 sheets and 5,000 rows per sheet. Search results are capped at 500. This is still not a full Windows Search index, OCR system, or semantic document index.

The API rejects actions unless the desktop sends an explicit approval flag. App launch requests resolve against the live Windows application catalogue. Classic apps are discovered through Start Menu shortcuts, Windows Start Apps, uninstall metadata, install locations and App Paths. Launches use the Windows Shell rather than constructing shell commands. If multiple installed apps match a request, NOVA asks you to choose.

Useful endpoints:
- `GET /computer/capabilities` — inspect allowlisted apps and approved roots.
- `POST /computer/actions` — execute one registered action after approval.
- `GET /computer/audit` — inspect recent local action records.

## Local model benchmarking

See [docs/LOCAL_MODEL_BENCHMARK.md](docs/LOCAL_MODEL_BENCHMARK.md) for a repeatable benchmark of models exposed by your local runtime. It measures median TTFT and total response time without sending prompts to a cloud service or changing NOVA's configuration.

## Tests

```powershell
pytest
```

## Safety direction

NOVA does not give a language model unrestricted shell or computer access. Computer tools are explicitly registered, narrowly scoped, logged, and gated by desktop approval. Model output is untrusted input, never executable authority.

## Roadmap

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for architecture and milestones.

## License

MIT. See [LICENSE](LICENSE).


### Response performance

NOVA exposes `POST /chat/stream` for server-sent token events, reuses its provider's HTTP connection pool, and reports time-to-first-token and total-generation timing. The desktop batches stream updates to reduce UI overhead.

The default local-chat settings are tuned for responsiveness:

- `NOVA_AI_MAX_TOKENS=512` limits generated output. Increase to 1024-2048 when you need longer explanations or code.
- `NOVA_AI_CONTEXT_MESSAGES=8` limits the previous conversation history sent with each prompt.
- `NOVA_AI_QWEN_NO_THINK=true` adds Qwen3's documented `/no_think` prompt switch for Qwen3 model IDs. Add `/think` to a message when you want deeper reasoning for that turn.
- `NOVA_AI_TOP_P=0.8` uses Qwen3's recommended non-thinking sampling value.

These settings are configurable in your private `.env`. Model residency is controlled by the local runtime, not NOVA's generic OpenAI-compatible adapter. If Bionic offers a keep-loaded or auto-unload setting, keep the model loaded while using NOVA. Actual token generation speed is still limited by the model, quantization, and available CPU/GPU acceleration.


### Natural-language computer requests

NOVA's first deterministic computer planner can route requests such as:

- "Find my physics assignment" — search filenames across accessible drives.
- "Search inside my files for thermodynamics" — search supported local text and document contents.
- "Open C:\\Users\\you\\Documents\\notes.txt" — ask before opening an explicit path.
- "Read C:\\Users\\you\\Documents\\notes.txt" — ask before reading; content is displayed locally and is not sent to the model.
- "List files in C:\\Users\\you\\Documents" — ask before listing a folder.

Every planned action is reviewed through a one-action confirmation dialog. The planner is intentionally deterministic at this stage: it does not execute model-generated commands, and it supports bounded multi-step plans for recognized Windows system and window actions. Every step is confirmed separately; the plan stops immediately if a step is cancelled or fails.


## Windows OS awareness (first integration layer)

NOVA exposes read-only information about the current Windows session:

- `GET /computer/system` — OS, hardware/runtime details, resource metrics via the core psutil dependency, and the foreground window.
- `GET /computer/processes` — bounded process inventory (PID, process name, status, resident memory); it deliberately omits command lines and environment variables.
- `GET /computer/windows` — visible top-level window titles and owning process IDs.
- `POST /computer/windows/actions` — focus, minimize, restore, or maximize a selected visible window after explicit approval.
- `POST /computer/system/volume` and `/computer/system/brightness` — adjust supported Windows audio/display hardware after confirmation.
- `POST /computer/windows/search` — open native Windows Search for a query after confirmation.

Process and resource metrics use the core psutil dependency. Window enumeration uses the Windows API directly. These endpoints do not terminate processes, inject input, capture screenshots, or bypass Windows permissions. The desktop also exposes a confirmed **Control a window** action: choose a visible window, then explicitly approve focusing/switching to it, minimizing, restoring, or maximizing it. The API supports only those four operations; it does not close apps or inject keyboard/mouse input. Window controls are Windows-only and require the target to remain a visible top-level window.
NOVA can also handle `set volume to 35`, `change brightness to 70%`, and `search Windows for physics notes`. Each is parsed into a fixed typed operation and confirmed before execution. Volume adjustment uses the optional `pycaw` Windows audio extra; install it with `pip install -e ".[windows]"`. Brightness control uses the Windows WMI interface and may not work with external monitors or every laptop panel. Windows Search opens the native indexed-search experience in Explorer; NOVA does not scrape or bypass its index.

The **Interact with an app** control uses Windows UI Automation (optional `pywinauto`) to inspect supported accessible controls in an open window. It can activate a single named enabled button, tab, menu item, hyperlink, checkbox, or radio button after a separate confirmation. The **Enter text into an app** control can enter up to 2,000 characters into one uniquely named, visible, enabled, non-password text field after confirmation. Password fields are excluded; entered text is not written to the audit log. Some applications expose few or no accessible controls.

NOVA now integrates with the Windows shell: it can minimize to the notification area, reopen with the global `Ctrl+Alt+Space` shortcut, optionally register itself to start at sign-in under the current user's Run key, and show native Windows toast notifications when a reply arrives while hidden. Right-click the tray icon to open NOVA, toggle startup, send a test notification, or quit. Closing the main window hides NOVA in the tray; use **Quit NOVA** to fully exit.

The Computer Controls panel also offers opt-in battery/power event monitoring. It checks battery level and charging state once per minute while the panel is open, and can notify at 20% or below or when the power connection changes. This is polling-based and is not a subscription to all Windows event channels. It stops when the panel closes.

The Computer Controls panel also offers temporary active-app awareness. It is off by default, polls the foreground window title only after you opt in, stops when the panel closes, and does not save titles or send them to the AI.

You can also use short natural-language window commands in chat, such as "Switch to Chrome", "Minimize Notepad", "Restore Explorer", or "Maximize Calculator". NOVA matches the request against currently visible window titles, asks you to choose if multiple windows match, and always asks for confirmation before changing a window.

