#ifndef AppVersion
  #error AppVersion must be supplied by the release script
#endif
#ifndef PayloadDir
  #error PayloadDir must be supplied by the release script
#endif
#ifndef ReleaseDir
  #error ReleaseDir must be supplied by the release script
#endif
#ifndef EditionSuffix
  #define EditionSuffix ""
#endif

[Setup]
AppId={{B8353E67-ECF3-4D65-9479-145AB815BFD8}
AppName=Img2Tex
AppVersion={#AppVersion}
AppPublisher=Img2Tex
AppVerName=Img2Tex {#AppVersion}
DefaultDirName={localappdata}\Programs\Img2Tex
DefaultGroupName=Img2Tex
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.19045
UninstallDisplayName=Img2Tex
UninstallDisplayIcon={app}\Img2Tex.exe
AppReadmeFile={app}\ReadMe.txt
SetupIconFile=..\..\src\img2tex\assets\app.ico
VersionInfoVersion={#AppVersion}.0
OutputDir={#ReleaseDir}
OutputBaseFilename=Img2Tex-{#AppVersion}-Windows-x64-Setup{#EditionSuffix}
Compression=lzma2/fast
SolidCompression=yes
LZMANumBlockThreads=4
CloseApplications=yes
RestartApplications=no
WizardStyle=modern
#ifdef Span
DiskSpanning=yes
DiskSliceSize=2000000000
#endif

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Img2Tex"; Filename: "{app}\Img2Tex.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Img2Tex"; Filename: "{app}\Img2Tex.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Img2Tex.exe"; Description: "{cm:LaunchProgram,Img2Tex}"; Flags: nowait postinstall skipifsilent

; User data is outside {app}. No broad uninstall deletion is permitted.
