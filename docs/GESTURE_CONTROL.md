# NOVA gesture control design

Gesture control is a separate, opt-in local input subsystem. It is intended to let
the user move the pointer, scroll, click, and drag items or windows without touching
the mouse. It must not be active by default.

## Initial gesture map

| Gesture | Action |
|---|---|
| Index finger extended | Move the pointer |
| Thumb and index finger pinched | Hold the left mouse button; move to drag |
| Release the pinch | Release the mouse button |
| Index and middle fingers extended | Scroll vertically |
| Open palm held briefly | Pause gesture control and release any held mouse button |
| Closed fist held briefly | Emergency stop / release all held input |

The user can recalibrate the camera area and cursor sensitivity. Pointer movement
uses smoothing and a bounded screen mapping so small hand tremors do not cause
large jumps.

## Runtime and hardware

- Use one hand and a reduced camera frame (target 640x480 at about 15 frames/sec).
- Prefer a lightweight MediaPipe Hands model with CPU inference; no dedicated GPU
  is assumed. The Intel UHD integrated graphics are not required for inference.
- Run camera capture and landmark inference on a worker thread, never on the Qt UI
  thread.
- Keep the camera stream in memory only. Do not save frames, record video, or send
  camera data to any AI provider.
- Provide a visible camera-active indicator and an immediate pause/stop control in
  the desktop UI and notification-area menu.
- Store the opt-in preference locally. Do not enable camera access on install or
  silently turn it on after an update.

## Input safety

The gesture subsystem may only move the pointer, scroll, and hold/release the
primary mouse button. It must not synthesize arbitrary keyboard input, run shell
commands, type text, or execute scripts. The open-palm and fist stop gestures
must always release a held mouse button. If camera frames stop arriving, hand
tracking confidence falls below threshold, or the worker fails, NOVA must release
all held input and pause the controller.

Dragging files or windows is a normal mouse drag and can change the desktop. The
controller must therefore show a clear opt-in explanation before enabling it and
must support an immediate manual stop. A future implementation should include a
short calibration screen and a visible pointer-control preview before allowing
drag gestures.

## Status

This document defines the first implementation target. Gesture tracking and
Windows pointer integration are not yet implemented or enabled.
