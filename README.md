# NOVA

**An open-source, hybrid AI desktop assistant for Windows.**

NOVA is a permission-first desktop assistant designed to combine local models, cloud AI providers, voice interaction, persistent memory, and carefully controlled computer tools.

> NOVA is under active development. The current repository contains the initial backend foundation; voice, desktop UI, model integrations, and computer-control tools are not implemented yet.

## Project principles

- **Hybrid intelligence:** use local models for lightweight/private tasks and cloud providers for tasks that benefit from stronger reasoning.
- **Local-first memory:** keep personal conversation data on the user's machine by default.
- **Permission before action:** tools must request authorization according to their risk level. Model output never grants itself permission.
- **Provider independence:** swap model providers without rewriting the assistant.
- **Open source:** build in public and make the system extensible.

## Planned architecture

```text
NOVA/
├── src/nova/
│   ├── api/             # Local HTTP API
│   ├── core/            # Orchestration and application logic
│   │   └── ai/          # Provider interfaces and model routing
│   ├── memory/          # Local conversation and preference storage
│   ├── permissions/     # Approval policies and action boundaries
│   └── tools/           # Explicitly registered computer tools
├── tests/
├── docs/
├── .env.example
├── pyproject.toml
└── README.md
```

## Hardware target

The first development target is a Windows laptop with an Intel Core i5-8350U, Intel UHD Graphics 620, and 16 GB RAM. Local model recommendations will be conservative and benchmarked on CPU; cloud inference remains optional.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer
- Git

## Run the backend

PowerShell:

```powershell
git clone https://github.com/ShrikrishnaSwami/NOVA.git
cd NOVA

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[dev]"

Copy-Item .env.example .env
uvicorn nova.main:app --reload
```

The local API will be available at `http://127.0.0.1:8000`.

- Health check: `GET http://127.0.0.1:8000/health`
- Interactive API docs: `http://127.0.0.1:8000/docs`

Run tests:

```powershell
pytest
```

## Configuration

NOVA reads optional settings from a local `.env` file. Never commit API keys or personal credentials. See [.env.example](.env.example).

The API binds to loopback (`127.0.0.1`) by default so it is not exposed to the local network.

## Safety model

NOVA will not provide an unrestricted shell to the language model. Computer actions will be exposed through a tool registry with explicit schemas, risk levels, approval checks, and audit records. Destructive or externally visible actions will require user approval. These controls are a design requirement, not an optional feature.

## Roadmap

- [x] Initial repository and MIT license
- [x] Minimal FastAPI backend and health endpoint
- [x] Environment-based configuration
- [ ] Provider interface and local/cloud model adapters
- [ ] SQLite conversation memory
- [ ] Permission manager and audit log
- [ ] Text chat experience
- [ ] Voice input and speech output
- [ ] Windows desktop interface
- [ ] Approved file, application, and system tools
- [ ] Plugin SDK and documentation

## Contributing

Issues and pull requests are welcome. Please read the project documentation before proposing changes to permissions, data handling, or computer-control behavior.

## License

NOVA is released under the [MIT License](LICENSE).
