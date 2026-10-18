; Inno Setup script for Structure Lab (run by IT once; supports /VERYSILENT)
[Setup]
AppName=Structure Lab
AppVersion=1.0.0
DefaultDirName={localappdata}\StructureLab
DefaultGroupName=Structure Lab
OutputDir=..\dist
OutputBaseFilename=StructureLab-Setup
PrivilegesRequired=lowest
Compression=lzma2
SolidCompression=yes

[Files]
; TODO: bootstrap Python (embeddable) + launcher.py + assets
Source: "launcher.py"; DestDir: "{app}\bootstrap"; Flags: ignoreversion
Source: "assets\*"; DestDir: "{app}\bootstrap\assets"; Flags: ignoreversion recursesubdirs

[Icons]
; TODO: shortcut runs pythonw.exe launcher.py
Name: "{autoprograms}\Structure Lab"; Filename: "{app}\bootstrap\python\pythonw.exe"; Parameters: """{app}\bootstrap\launcher.py"""
