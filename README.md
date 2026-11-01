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
- Conversation history held in the desktop session (persistent memory is a later milestone).

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

## Tests

```powershell
pytest
```

## Safety direction

NOVA will not give a language model unrestricted shell or computer access. Future tools will be explicitly registered, narrowly scoped, logged, and gated by user approval for sensitive actions. Model output is untrusted input, never executable authority.

## Roadmap

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for architecture and milestones.

## License

MIT. See [LICENSE](LICENSE).
