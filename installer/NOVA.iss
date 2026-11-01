; NOVA per-user Windows installer. Build after scripts/build_windows.ps1.
#define MyAppName "NOVA"
#define MyAppVersion "0.1.7"
#define MyAppPublisher "NOVA contributors"
#define MyAppExeName "NOVA.exe"

[Setup]
AppId={{A2E9C2D7-2B70-4D18-9E6D-64C20C1A2F71}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\NOVA
DefaultGroupName=NOVA
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=NOVA-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64compatible
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start NOVA automatically when you sign in to Windows (runs in the notification area)"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
Source: "..\dist\NOVA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\.env.example"; DestDir: "{app}"; DestName: ".env.example"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "NOVA"; ValueData: """{app}\{#MyAppExeName}"" --background"; Tasks: startup; Flags: uninsdeletevalue

[Icons]
Name: "{group}\NOVA"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\NOVA (Background)"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--background"; WorkingDir: "{app}"
Name: "{autodesktop}\NOVA"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch NOVA"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  UserConfigDir: String;
  SourceEnv: String;
  TargetEnv: String;
begin
  if CurStep = ssPostInstall then
  begin
    UserConfigDir := ExpandConstant('{userappdata}\NOVA');
    ForceDirectories(UserConfigDir);
    SourceEnv := ExpandConstant('{app}\.env.example');
    TargetEnv := UserConfigDir + '\.env';
    if (not FileExists(TargetEnv)) and FileExists(SourceEnv) then
      FileCopy(SourceEnv, TargetEnv, False);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'NOVA');
end;
