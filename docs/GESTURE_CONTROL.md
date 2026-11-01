# NOVA gesture control design

**Status: Design only — not implemented.**

Gesture control is a possible future, opt-in local input subsystem. It is not currently available in NOVA 0.1.7. The gestures and safeguards below are design requirements, not working product features.

## Proposed gesture map

| Gesture | Intended action |
|---|---|
| Index finger extended | Move the pointer |
| Thumb and index finger pinched | Hold the left mouse button; move to drag |
| Release the pinch | Release the mouse button |
| Index and middle fingers extended | Scroll vertically |
| Open palm held briefly | Pause and release held input |
| Closed fist held briefly | Emergency stop and release held input |

## Proposed runtime and hardware

- Use one hand and a reduced camera frame (target 640×480 at about 15 frames/sec).
- Evaluate a lightweight local hand-landmark model with CPU inference; no dedicated GPU should be assumed.
- Run camera capture and inference on a worker thread, never on the Qt UI thread.
- Keep camera frames in memory only. Do not save frames, record video, or send camera data to an AI provider.
- Provide a visible camera-active indicator and immediate pause/stop controls.
- Store opt-in preference locally. Never enable camera access during installation or silently after an update.

## Required input safety

A first implementation should be limited to pointer movement, scrolling, and holding/releasing the primary mouse button. It must not synthesize arbitrary keyboard input, run shell commands, type text, or execute scripts.

Emergency-stop gestures and manual stop controls must release any held mouse button. If frames stop arriving, tracking confidence falls below threshold, or the worker fails, the controller must release all held input and pause.

Dragging files or windows can change the desktop. The UI must explain this before enabling drag gestures and provide an immediate manual stop. A calibration screen and pointer preview should precede activation.

## Status

No gesture tracking, camera integration, or Windows pointer-control implementation is included in the current release. Do not advertise this as an available NOVA feature until implemented and tested.
