# Local voice setup

NOVA's voice features run locally:

- **Speech input:** Vosk offline speech recognition.
- **Wake word:** local constrained-grammar Vosk recognition using the phrase **"Hey NOVA"**.
- **Speech output:** pyttsx3 using voices already installed in Windows (SAPI5).
- **Microphone capture:** sounddevice / PortAudio.
- **No cloud speech APIs:** audio is not uploaded by NOVA.

## Installed Windows application

The Windows packaging build downloads and bundles the small English model
`vosk-model-small-en-us-0.15` beside NOVA.exe. The installed app finds this
model automatically. You do not need to edit source code, run a download
command, or set `NOVA_VOSK_MODEL_PATH` for the packaged app.

During installation, NOVA can be configured to start with Windows in the
notification area. Enable **Wake word** in the desktop composer or open **NOVA settings** and
turn on **Hey NOVA**. The settings screen lets you choose an input device and
run a microphone test. The preference is saved locally, so on subsequent
sign-ins NOVA starts hidden, loads its bundled model, and listens for "Hey
NOVA". Wake-word standby is off by default and can be disabled from the
composer or settings. Microphone audio remains on-device and is never uploaded.

When activated, NOVA stops any current speech playback, captures your command,
and sends it through the normal chat and approved-tool pipeline. When a reply
arrives, NOVA reads it aloud and then returns to wake-word standby. Push-to-talk
remains available as an alternative.

## Development checkout

Install the optional packages:

```powershell
pip install -e ".[desktop,voice]"
```

Download an English model from the official Vosk model page:
https://alphacephei.com/vosk/models

For a modest download, use `vosk-model-small-en-us-0.15`. Extract it to:

```text
C:\NOVA\models\vosk-model-small-en-us-0.15
```

NOVA looks for that folder automatically in a development checkout. You can
override it in your private `.env` file:

```dotenv
NOVA_VOSK_MODEL_PATH=C:\NOVA\models\vosk-model-small-en-us-0.15
```

## Troubleshooting

- **Model not found:** verify the model folder contains Vosk subfolders such as `am`, `conf`, and `graph`.
- **Microphone unavailable:** check Windows Settings → Privacy & security → Microphone and allow desktop-app access.
- **No audio device / PortAudio error:** check Windows input-device selection and restart NOVA.
- **Speech output unavailable:** verify that Windows has an installed speech voice. pyttsx3 uses the local SAPI5 engine.
- **Poor recognition:** try a larger Vosk model from the official model list; it uses more disk space and RAM.

Voice features are optional. Text chat remains available without them.
