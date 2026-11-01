# Windows installation and lifecycle

## Distribution model

NOVA is distributed as a per-user Windows desktop application. It is not installed as a LocalSystem service. The desktop must run in the signed-in user's interactive session to interact with that user's windows, UI Automation providers, microphone, and notification area.

The desktop manages a separate FastAPI backend process bound to loopback. When launched, it checks the local health endpoint and starts its own backend when required. It does not need a terminal or manual Uvicorn command for ordinary installed use.

## Download the installer

The Windows installer workflow builds two artifacts:

- **NOVA-Windows-Installer** — a ZIP containing the per-user setup executable.
- **NOVA-Portable-Windows** — a ZIP containing the complete portable application folder.

To install:

1. Open the repository's [Windows installer Actions workflow](https://github.com/ShrikrishnaSwami/NOVA/actions/workflows/windows-installer.yml).
2. Open the latest successful run for the desired commit/version.
3. Scroll to **Artifacts**.
4. Download and extract **NOVA-Windows-Installer**.
5. Run the included `NOVA-Setup-<version>.exe`.

Artifacts appear only after the relevant workflow jobs complete successfully. A queued, in-progress, or failed workflow does not provide a verified installer.

For the portable build, extract the full archive and run `NOVA\NOVA.exe`. Keep the complete folder intact; the executable depends on bundled libraries and resources beside it.

Tagged `v*` releases may also publish installer and portable files as GitHub Release assets when the workflow's release step succeeds.

## Build locally (contributors)

Requirements: Windows 10/11 x64, Python version supported by the current project/CI configuration, Git, and Inno Setup 6.

From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,desktop,voice,windows,documents,build]"
pytest -q
.\scripts\build_windows.ps1
& "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe" "installer\NOVA.iss"
```

The current source milestone is **0.1.7**. The versioned installer filename is generated from the package/installer version at build time; check the workflow artifact for the exact filename rather than assuming a build has completed.

## Installation behaviour

- Installs per-user under `%LOCALAPPDATA%\Programs\NOVA`.
- Does not require administrator privileges.
- Creates Start Menu shortcuts and can create a desktop shortcut.
- Can be uninstalled through Windows Settings → Apps → Installed apps.
- Bundles the small English Vosk model used by local voice mode.
- Stores user settings and persistent data outside the install directory.

## User data locations

- Settings: `%APPDATA%\NOVA\.env`
- Preferences: `%APPDATA%\NOVA\preferences.json`
- SQLite database: `%LOCALAPPDATA%\NOVA\nova_memory.sqlite3`
- Installed program: `%LOCALAPPDATA%\Programs\NOVA`

The installer copies the example configuration only if a user settings file does not already exist. Upgrades are designed not to overwrite user settings or the SQLite database. Back up these files before manually modifying or removing user data.

## Desktop session lifecycle

- One desktop instance is allowed per user profile.
- The app can start hidden in the notification area.
- Closing the main window hides NOVA; the tray menu's **Quit NOVA** action exits it.
- The desktop checks `/health` before starting a backend child process.
- It stops only the backend child process it owns.
- Automatic backend startup uses a loopback address.
- The sign-in startup option changes only the current user's startup entry.
- `Ctrl+Alt+Space` uses the Windows RegisterHotKey API; NOVA does not install a global keyboard hook.

## Notifications and microphone

NOVA-generated notifications are optional and user-controlled. Windows notification settings remain authoritative. The current installer does not declare the restricted `userNotificationListener` capability and NOVA does not read other applications' notifications.

Wake-word listening is off by default and must be enabled by the user. Microphone selection and testing are available in settings. Local Vosk recognition is used; audio is not sent to a cloud speech API.

## Automation and security boundary

The shared automation engine exposes a finite registry of typed actions. It validates the entire chain before execution, limits chains to five steps, and stops on cancellation or failure. The desktop shows explicit confirmations. Typed API endpoints independently validate approval flags and operation-specific parameters.

NOVA runs as the signed-in user. It does not install a privileged service, disable Defender/UAC, inject into unrelated processes, or execute model-generated shell commands. User data is kept outside the install directory so updates can preserve it.
