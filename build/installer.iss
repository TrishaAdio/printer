; Inno Setup script for GlassPrint.
;
; Installs the directory build, which starts immediately, rather than the single
; file build which unpacks itself on every launch. Per user by default so no
; administrator prompt is needed; pass /ALLUSERS to install machine wide.
;
; Build:  iscc build\installer.iss

#define AppName "GlassPrint"
#define AppVersion "1.0.0"
#define AppPublisher "GlassPrint"
#define AppExe "GlassPrint.exe"

[Setup]
AppId={{8C2F1A54-4C93-4E1F-9B27-6F1D4E7A2C10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
OutputDir=..\dist\installer
OutputBaseFilename=GlassPrint-{#AppVersion}-setup
SetupIconFile=..\app\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
; Windows 10 1809 is the floor, which is what Qt 6 itself requires.
MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "sendto"; Description: "Add to the Send to menu, so files can be printed from Explorer"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\GlassPrint\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{usersendto}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: sendto

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Logs and the render cache are regenerated, so they go. Settings and history are
; left behind on purpose: reinstalling should not lose someone's print defaults.
Type: filesandordirs; Name: "{userappdata}\GlassPrint\logs"
Type: filesandordirs; Name: "{userappdata}\GlassPrint\cache"
