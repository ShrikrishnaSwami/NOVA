# NOVA model tools and voice

This document covers the current tool-planning and voice implementation. For the broader component map, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Model-guided tool planning

NOVA can ask the configured OpenAI-compatible model to propose structured tool calls. The proposal is validated against the live registered tool schemas before the desktop offers it for approval.

Runtime endpoints:

- `GET /runtime/tools` — registered tool inventory.
- `POST /runtime/tools/plan` — request a proposal with a message.
- `POST /runtime/tools/execute` — execute a validated chain only when `approved: true` is supplied.

The desktop chat flow requests a plan, displays the proposed operations and arguments, and requires the user to approve before execution. If planning fails or no tools are proposed, ordinary chat remains available. Actual tool results are sent back to the model so NOVA can describe the outcome rather than assume success.

### Validation and execution rules

- Maximum of five tool calls in a chain.
- The entire chain is validated before any handler runs.
- Only registered tool names and declared arguments are accepted.
- Unknown tools, malformed arguments, and invalid types fail closed.
- Each handler must return the expected structured result.
- Execution stops on the first failed step; later steps are marked skipped.
- Partial results are preserved so the assistant can accurately report what completed.
- Explicit approval is required; model text cannot approve its own proposal.

The registry includes read-only system and visible-window tools. Some example subsystem tools are simulations and are labelled as such. They do not control physical aerospace, energy, thermal, or holographic hardware.

Mutating Windows actions use separate typed computer-control APIs and desktop confirmation dialogs. NOVA does not provide arbitrary shell execution, arbitrary Python execution, eval, or unrestricted process termination.

## Local voice

The Windows desktop supports local voice input and output:

- **Input capture:** sounddevice / PortAudio.
- **Speech recognition:** Vosk offline model.
- **Wake phrase:** constrained local grammar, default phrase “Hey NOVA”.
- **Speech output:** pyttsx3 using installed Windows SAPI voices.
- **Playback interruption:** an active speech response can be stopped when a new wake-word interaction starts.
- **Fallback:** push-to-talk remains available.

The installed Windows build bundles `vosk-model-small-en-us-0.15`. Microphone selection and a microphone test are available in desktop settings. Wake-word standby is opt-in and can be disabled from the UI/settings. The microphone remains active while wake-word mode is enabled, so use the visible desktop controls to stop it when not needed.

NOVA processes microphone audio locally and does not send it to a cloud speech-recognition service.

## Privacy and safety

- Tool proposals are never executed solely because the model requested them.
- Tool handlers remain limited to registered contracts.
- Wake-word listening is not enabled by default.
- The app must make microphone state controllable by the user.
- Voice features do not grant extra computer permissions.
- Arbitrary shell commands, generated scripts, and unrestricted desktop actions are not exposed.
