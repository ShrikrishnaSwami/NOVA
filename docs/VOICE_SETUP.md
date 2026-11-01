# Local voice setup

NOVA's Windows voice features use local components:

- **Speech input:** Vosk offline speech recognition.
- **Wake word:** local constrained-grammar recognition using “Hey NOVA”.
- **Speech output:** pyttsx3 with voices installed in Windows (SAPI5).
- **Microphone capture:** sounddevice / PortAudio.
- **Cloud speech:** NOVA does not upload microphone audio to a cloud speech service.

## Installed Windows application

The packaged Windows build bundles the small English Vosk model `vosk-model-small-en-us-0.15`. The installed app locates this model automatically; you do not need to download it or set `NOVA_VOSK_MODEL_PATH` for the packaged application.

1. Open NOVA settings.
2. Select the microphone/input device you want to use.
3. Use the microphone test to verify input.
4. Enable **Hey NOVA** only if you want hands-free wake-word standby.
5. You can disable wake-word listening again from the desktop controls/settings.

Wake-word standby is opt-in. When active, the microphone remains in use to detect the wake phrase. The desktop can interrupt current speech playback, capture the next command, and route it through the normal chat and approval flow. Push-to-talk remains available as an alternative.

You can optionally configure NOVA to start hidden at Windows sign-in. If both sign-in startup and wake-word listening are enabled, NOVA can start in the notification area and listen locally. Review these preferences before enabling them.

## Development checkout

For source development, install the optional dependencies:

```powershell
pip install -e ".[desktop,voice]"
```

Download an English model from the [official Vosk model page](https://alphacephei.com/vosk/models). The small model is `vosk-model-small-en-us-0.15`. Extract it into a models folder in your development checkout, or configure the model path in your private `.env`:

```dotenv
NOVA_VOSK_MODEL_PATH=C:\NOVA\models\vosk-model-small-en-us-0.15
```

The development model path is not required for the packaged Windows installer.

## Troubleshooting

- **Model not found:** check that the model directory contains Vosk folders such as `am`, `conf`, and `graph`.
- **Microphone unavailable:** open Windows Settings → Privacy & security → Microphone and allow desktop-app access.
- **No audio device / PortAudio error:** check the selected Windows input device and restart NOVA.
- **Speech output unavailable:** confirm that Windows has an installed speech voice. pyttsx3 uses the local SAPI5 engine.
- **Poor recognition:** try a larger Vosk model; larger models use more storage and memory.
- **Wake phrase not detected:** verify the selected microphone, input level, and that wake-word mode is enabled.

Voice is optional. Text chat remains available without a microphone or speech output.
