# NOVA architecture

## Initial runtime

The first milestone is a local FastAPI process. The desktop client will communicate with this process over loopback HTTP. The API is bound to `127.0.0.1` by default.

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
- Tools expose narrow, typed operations rather than arbitrary system access.
- Every tool has a declared risk level and permission policy.
- User approval is checked by application code, never inferred from model text.
- Secrets are read from local environment configuration and are never stored in source control.
- The local API must remain loopback-only unless a future authenticated network mode is explicitly designed.

## Development milestones

1. API and configuration foundation.
2. Provider abstraction and local/cloud routing.
3. SQLite memory with explicit retention and deletion controls.
4. Permission manager, tool registry, and audit log.
5. Streaming text conversation.
6. Voice pipeline and desktop UI.
7. Small, allowlisted Windows tools.
