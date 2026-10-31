# NOVA architecture

## Runtime

The first milestone is a local FastAPI process. The future desktop client will communicate with this process over loopback HTTP. The API binds to `127.0.0.1` by default.

## AI provider layer

NOVA defines a provider contract in `src/nova/core/ai/types.py`. Provider implementations live behind that contract, so conversation orchestration does not depend on a particular model vendor or runtime.

The current adapters are:

- `echo`: safe setup mode that lets a fresh installation exercise the chat API without credentials.
- `openai_compatible`: adapter for local model servers and compatible hosted APIs using the chat-completions request format. It can connect to a local runtime such as LM Studio or llama.cpp server, or a compatible cloud endpoint.

Provider selection is controlled by environment variables. No API key is required for local endpoints that do not use authentication. Credentials belong in the local `.env` file and must never be committed.

## Planned request flow

```text
Desktop UI (future)
      |
      v
Local API
      |
      v
Conversation orchestrator
      |
      +---- Model router ---- Local model adapter
      |                   \-- Cloud model adapter
      |
      +---- Memory service ---- SQLite (planned)
      |
      +---- Tool registry
                 |
                 v
          Permission manager
                 |
          User approval gate
                 |
                 v
           Tool execution
```

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
3. Local model runtime and cloud provider-specific adapters.
4. SQLite memory with explicit retention and deletion controls.
5. Permission manager, tool registry, and audit log.
6. Streaming text conversation.
7. Voice pipeline and desktop UI.
8. Small, allowlisted Windows tools.
