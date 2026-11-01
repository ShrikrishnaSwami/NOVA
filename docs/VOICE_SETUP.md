# Local voice setup

NOVA's optional voice features are fully local:

- **Speech input:** Vosk offline speech recognition.
- **Speech output:** pyttsx3 using voices already installed in Windows (SAPI5).
- **Microphone capture:** sounddevice / PortAudio.
- **No cloud speech APIs:** audio is not uploaded by NOVA.

Voice input is deliberately push-to-talk. NOVA does not keep the microphone open in the background and does not implement an always-listening wake word.

## 1. Install optional packages

From the repository root with the virtual environment active:

```powershell
pip install -e ".[desktop,voice]"
```

## 2. Download an offline Vosk model

Download an English model from the official Vosk model page:

https://alphacephei.com/vosk/models

For a modest download, start with **vosk-model-small-en-us-0.15**. Extract the archive somewhere permanent, for example:

```text
C:\NOVA\models\vosk-model-small-en-us-0.15
```

The folder selected by the environment variable must contain Vosk model subfolders such as `am`, `conf`, `graph`, and `ivector` (if present). Do not point to the ZIP file.

## 3. Configure the model folder

Set this in the same PowerShell window before starting NOVA:

```powershell
$env:NOVA_VOSK_MODEL_PATH = "C:\NOVA\models\vosk-model-small-en-us-0.15"
nova-desktop
```

Alternatively, add this variable to your private `.env` file (do not commit `.env`):

```dotenv
NOVA_VOSK_MODEL_PATH=C:\NOVA\models\vosk-model-small-en-us-0.15
```

The desktop process must be started after setting the variable.

## 4. Use voice

- Click **Talk** and speak a short phrase.
- Vosk detects the end of the phrase and fills the message composer with the transcription.
- NOVA sends the recognized text through the existing chat pipeline.
- Click **Stop listening** to stop capture manually.
- Click **Read last reply** to speak the most recent NOVA response through a locally installed Windows voice.

The first voice model load can take a few seconds. Windows may show a microphone permission prompt; allow microphone access for the desktop app/terminal.

## Troubleshooting

- **No Vosk model found:** check that `NOVA_VOSK_MODEL_PATH` points to the extracted model directory, not its parent or ZIP.
- **Microphone unavailable:** check Windows Settings → Privacy & security → Microphone and ensure desktop apps can access it. Close other apps that may exclusively hold the microphone.
- **No audio device / PortAudio error:** check Windows input device selection and restart NOVA after changing it.
- **Speech output unavailable:** verify that Windows has an installed speech voice. pyttsx3 uses the local SAPI5 engine.
- **Poor recognition:** try a larger Vosk model from the official model list; it will use more disk space and RAM.

Voice features are optional. NOVA's text chat works normally when these packages or the Vosk model are not installed.