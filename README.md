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
- Permission-gated computer tools that discover Windows Start Menu app shortcuts and explicitly approved folders.
- Local audit log for completed or blocked computer operations.

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

Start the backend in PowerShell window 1:

```powershell
uvicorn nova.main:app --reload
```

Start the desktop interface in PowerShell window 2:

```powershell
nova-desktop
```

The desktop client connects to `http://127.0.0.1:8000`. To use a different backend address, set `NOVA_API_URL` before launching it:

```powershell
$env:NOVA_API_URL = "http://127.0.0.1:8000"
nova-desktop
```

You can also use the backend without the desktop client:

- Health: http://127.0.0.1:8000/health
- API docs: http://127.0.0.1:8000/docs
- AI status: http://127.0.0.1:8000/system/ai

## Local voice (optional)

NOVA can transcribe microphone input locally with Vosk and read responses aloud using the installed Windows speech voices through pyttsx3. Voice input is push-to-talk; it does not continuously listen or use a wake word. Audio is processed on the device and is not sent to a cloud speech service. See [docs/VOICE_SETUP.md](docs/VOICE_SETUP.md) for installation and model setup. Install the optional dependencies with `pip install -e ".[desktop,voice]"`.

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

Open **Computer controls** in the desktop sidebar. NOVA currently supports:

- Open Notepad, Calculator, Paint, or File Explorer from a fixed application allowlist.
- List folders, search file/folder names, and read selected text files inside explicitly approved roots.
- Ask for a separate confirmation before every operation.
- Keep a local audit record of action type, safe parameters, outcome, and timestamp. File contents are never written to the audit log.

File access is disabled by default. Add only folders you want NOVA to access to your private `.env` file. Separate multiple paths with semicolons:

```dotenv
NOVA_COMPUTER_ALLOWED_ROOTS=C:\\Users\\YourName\\Documents;C:\\Users\\YourName\\Desktop
```

Replace the example paths with real folders on your computer, then restart the backend. The desktop dialog shows the active approved roots. NOVA can read only TXT, Markdown, Python, JSON, CSV, LOG, YAML, TOML, and INI files up to 64 KB. Search results are capped at 200. Paths are resolved and checked against approved roots to prevent traversal and symlink escapes.

The API rejects operations unless the desktop sends an explicit approval flag. Simple, exact app-launch phrases such as “open calculator”, “launch Notepad”, and “start Paint” are recognized locally and routed through the same approval prompt rather than sent to the model. Other requests still use normal chat. No arbitrary shell, PowerShell, command execution, or model-selected executable paths are exposed.

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
