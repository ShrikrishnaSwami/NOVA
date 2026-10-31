# NOVA

NOVA is an open-source hybrid AI desktop assistant for Windows, built around voice, memory, local and cloud intelligence, and permission-based computer control.

The project is in active early development. The current release is a local Python API foundation with a provider-independent chat layer.

## Current capabilities

- Local FastAPI backend bound to `127.0.0.1`.
- Health endpoint at `/health`.
- Interactive API documentation at `/docs`.
- Chat endpoint at `/chat`.
- Provider status at `/system/ai`.
- Setup mode that works without API keys.
- OpenAI-compatible adapter for local model servers and compatible hosted APIs.
- Client-controlled conversation history is restricted to user and assistant messages.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer (Python 3.13 is supported)
- Git

## Run locally

```powershell
git clone https://github.com/ShrikrishnaSwami/NOVA.git
cd NOVA

py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[dev]"

Copy-Item .env.example .env
uvicorn nova.main:app --reload
```

If PowerShell blocks activation, run this in the same terminal before activating:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Open:

- Health: http://127.0.0.1:8000/health
- API docs: http://127.0.0.1:8000/docs
- AI status: http://127.0.0.1:8000/system/ai

## Try the chat endpoint

In the API docs, open `POST /chat`, choose **Try it out**, and submit:

```json
{
  "message": "Hello, NOVA",
  "history": []
}
```

A fresh installation uses `echo` setup mode. This verifies the conversation API but is not an actual language model.

## Connect a model

NOVA's `openai_compatible` provider can connect to a local model server or a compatible hosted API. Configure these values in your local `.env` file:

```dotenv
NOVA_AI_PROVIDER=openai_compatible
NOVA_AI_MODEL=your-model-id
NOVA_AI_BASE_URL=http://127.0.0.1:1234/v1
NOVA_AI_API_KEY=
```

Use the base URL, model ID, and key required by the model server or cloud provider. Never commit `.env` or publish API keys. The default URL is a common local-server address; it does not mean a model server is already installed or running.

## Tests

```powershell
pytest
```

## Safety direction

NOVA will not give a language model unrestricted shell or computer access. Future tools will be explicitly registered, permission-scoped, and gated by user approval for sensitive actions.

## Roadmap

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the architecture and milestones.

## License

MIT. See [LICENSE](LICENSE).
