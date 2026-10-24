; Inno Setup 6 script for Structure Lab (per-user install, no admin rights, supports /VERYSILENT).
; Build with: .\runtime\python\python.exe tools\build.py --installer
; (build.py passes AppVersion, RuntimeId and StageDir; the defaults below are only for manual runs)

#ifndef AppVersion
  ; placeholder only: build.py always passes the real version (from src\version.py)
  #define AppVersion "0.0.0"
#endif
#ifndef RuntimeId
  #define RuntimeId "dev"
#endif
#ifndef StageDir
  #define StageDir "..\dist\stage"
#endif

#ifexist StageDir + "\bootstrap\app.ico"
  #define HasIcon
#endif
#ifdef HasIcon
  #define IconParam "; IconFilename: ""{app}\bootstrap\app.ico"""
#else
  #define IconParam ""
#endif

[Setup]
AppId={{B7C1F5A2-5D3E-4B7A-9C41-2A6E0F8D1C37}
AppName=Structure Lab
AppVersion={#AppVersion}
AppPublisher=Structure Lab
DefaultDirName={localappdata}\Structure Lab
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableWelcomePage=yes
DisableReadyPage=yes
DisableFinishedPage=no
PrivilegesRequired=lowest
; like the VSCode user installer, but without an entry in Programs and Features
Uninstallable=no
CreateUninstallRegKey=no
OutputBaseFilename=StructureLab-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
#ifdef HasIcon
SetupIconFile={#StageDir}\bootstrap\app.ico
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
; bootstrap (python + launcher.py + initial.json), first runtime and first app version
Source: "{#StageDir}\bootstrap\*"; DestDir: "{app}\bootstrap"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
; settings.json holds the server path; a re-install must not overwrite a user/IT edit
Source: "{#StageDir}\settings.json"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{userprograms}\Structure Lab"; Filename: "{app}\bootstrap\python\pythonw.exe"; Parameters: """{app}\bootstrap\launcher.py"""; WorkingDir: "{app}"; Comment: "Structure Lab"; AppUserModelID: "StructureLab.App"{#IconParam}
Name: "{userdesktop}\Structure Lab"; Filename: "{app}\bootstrap\python\pythonw.exe"; Parameters: """{app}\bootstrap\launcher.py"""; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "StructureLab.App"{#IconParam}

[Run]
Filename: "{app}\bootstrap\python\pythonw.exe"; Parameters: """{app}\bootstrap\launcher.py"""; WorkingDir: "{app}"; Description: "Start Structure Lab"; Flags: nowait postinstall skipifsilent
