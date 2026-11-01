$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --upgrade pip
python -m pip install -e ".[desktop,voice,windows,documents,build]"

$pyinstallerArgs = @(
  "--noconfirm", "--clean", "--onedir", "--windowed",
  "--name", "NOVA", "--paths", "src",
  "--collect-all", "PySide6",
  "--collect-all", "pywinauto",
  "--collect-all", "pycaw",
  "--collect-all", "winotify",
  "--collect-all", "vosk",
  "--collect-all", "sounddevice",
  "--collect-all", "pyttsx3",
  "--collect-all", "comtypes",
  "--hidden-import", "nova.main",
  "--hidden-import", "nova.service",
  "--hidden-import", "uvicorn.logging",
  "--hidden-import", "uvicorn.loops.auto",
  "--hidden-import", "uvicorn.protocols.http.auto",
  "--hidden-import", "uvicorn.lifespan.on",
  "scripts/nova_entry.py"
)
python -m PyInstaller @pyinstallerArgs

if (-not (Test-Path "dist/NOVA/NOVA.exe")) {
  throw "PyInstaller did not produce dist/NOVA/NOVA.exe"
}
# Bundle the small, local English Vosk model so voice works after installation
# without asking the user to download model files or edit source code.
$modelName = "vosk-model-small-en-us-0.15"
$modelArchive = Join-Path $env:TEMP "$modelName.zip"
$modelUrl = "https://alphacephei.com/vosk/models/$modelName.zip"
$modelExtract = Join-Path $env:TEMP "nova-vosk-model"
Invoke-WebRequest -Uri $modelUrl -OutFile $modelArchive
if (Test-Path $modelExtract) { Remove-Item $modelExtract -Recurse -Force }
Expand-Archive -Path $modelArchive -DestinationPath $modelExtract -Force
Copy-Item (Join-Path $modelExtract $modelName) (Join-Path (Resolve-Path "dist/NOVA") $modelName) -Recurse -Force
Remove-Item $modelArchive -Force
Remove-Item $modelExtract -Recurse -Force

Write-Host "NOVA packaged successfully at dist/NOVA"
