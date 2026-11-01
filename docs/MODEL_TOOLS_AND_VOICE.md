# NOVA model tools and hands-free voice

## Model-guided tool planning

NOVA now has a model-guided planning primitive at `nova.core.runtime.agent.propose_tools`.
It asks the configured OpenAI-compatible model for a JSON proposal, then validates every
tool name and argument against the live `ToolRegistry` schema.

The planner never executes a tool. The runtime API exposes:

- `GET /runtime/tools` — registered tool inventory.
- `POST /runtime/tools/plan` — request a model-generated proposal using
  `{"message":"..."}`.
- `POST /runtime/tools/execute` — execute a validated chain only when
  `approved: true` is supplied.

A chain is limited to five calls. The registry validates the entire chain before
running the first handler. Unknown tool names, extra arguments, missing required
arguments, invalid enum values, and incompatible primitive types are rejected.
The default registry now includes real read-only tools for system overview,
visible process inventory, foreground-window details, and visible windows, as
well as simulated aerospace, smart-grid, thermal, and holographic subsystems.
The simulations do not control physical hardware. The current model registry
does not yet expose mutating Windows actions; those remain on the existing
permission-scoped Computer Controls path.

The desktop chat now requests a model plan before ordinary chat, displays a
confirmation dialog when tools are proposed, executes only after approval, and
sends the actual tool results back to the model for a final response. If planning
fails or the model returns no tools, NOVA falls back to ordinary chat. Model-
generated plans remain untrusted until reviewed by the user. Qwen3 models served
through Bionic may vary in JSON reliability; invalid output fails closed.

## Local wake-word session

`nova.core.voice.WakeWordSession` provides a continuous local Vosk listener.
It uses a constrained wake grammar (default: `hey nova`), switches to a general
Vosk recognizer after activation, emits one utterance, and returns to wake-word
standby. Audio remains on the local machine.

The session accepts callbacks for wake detection, recognized utterances, and
errors. The wake callback is the intended hook for interrupting speech playback.

This is currently a reusable engine component, not yet connected to the desktop
window's voice controls. The existing desktop push-to-talk and read-last-reply
features remain unchanged. A complete interruptible desktop voice experience
still requires lifecycle/UI integration, playback cancellation, visible
microphone state, and end-to-end Windows testing.

## Safety and privacy

- No audio upload or cloud speech service is used by this component.
- The microphone remains active while the wake session is running; the desktop
  must visibly indicate this and provide an immediate stop control before it is
  enabled by default.
- Wake-word activation is opt-in; push-to-talk remains available.
- Tool proposals never execute automatically.
- Tool handlers remain constrained by the registry; arbitrary shell, code
  execution, and unrestricted desktop actions are not exposed.
