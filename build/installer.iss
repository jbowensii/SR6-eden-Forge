; Inno Setup — Shadowrun 6th World Catalog Builder
;
;   ISCC.exe build\installer.iss
;
; Driven by build\build_release.py, which passes the version and signs both the
; application executable and this installer afterwards.

#define AppName      "Shadowrun 6th World Catalog Builder"
#define AppShort     "SR6CatalogBuilder"
#define AppPublisher "John Bowens"
#define AppURL       "https://github.com/jbowensii/SR6-eden-Forge"
#ifndef AppVersion
  #define AppVersion "0.5.0"
#endif

[Setup]
AppId={{7C3F1E22-8A44-4B96-9F0D-5E2B1A6C4D31}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={autopf}\{#AppShort}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
InfoBeforeFile=installer-readme.txt
OutputDir=..\export\dist
OutputBaseFilename={#AppShort}_Setup_v{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; per-user by default: no elevation prompt, and it only ever writes to places
; the user already owns
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
UninstallDisplayName={#AppName}
SetupIconFile=

; Wizard artwork. Several sizes each so Windows picks one per display scaling
; rather than stretching a single 100% image, which on a 200% display looks
; exactly as bad as it sounds. BMP rather than PNG: PNG wizard images need
; Inno 6.3+, and BMP works everywhere — the figure is composited onto the
; app's own panel colour first, since BMP carries no alpha.
WizardImageFile=wizard\wizard-164x314.bmp,wizard\wizard-192x386.bmp,wizard\wizard-256x482.bmp,wizard\wizard-328x628.bmp
WizardSmallImageFile=wizard\small-55x55.bmp,wizard\small-64x68.bmp,wizard\small-92x97.bmp,wizard\small-110x110.bmp
WizardImageStretch=no
WizardImageAlphaFormat=none

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
    GroupDescription: "Shortcuts:"

[Files]
; the frozen one-folder build, verbatim
Source: "dist\SR6CatalogBuilder\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
; the pipeline the app drives
Source: "..\extractor\*"; DestDir: "{app}\extractor"; \
    Flags: ignoreversion recursesubdirs; Excludes: "__pycache__"
Source: "..\tools\*.py"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\schemas\*"; DestDir: "{app}\schemas"; Flags: ignoreversion recursesubdirs
Source: "..\site\*"; DestDir: "{app}\site"; \
    Flags: ignoreversion recursesubdirs; \
    Excludes: "node_modules\*,*.log,dist\*"
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\NOTICE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\SR6CatalogBuilder.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\SR6CatalogBuilder.exe"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\SR6CatalogBuilder.exe"; \
    Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller and Python leave these behind; the user's data is NOT touched —
; it lives in the workspace they chose and in %APPDATA%, and removing either
; would delete work the installer never created
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\extractor\__pycache__"
Type: filesandordirs; Name: "{app}\tools\__pycache__"

[Messages]
WelcomeLabel2=This installs the Catalog Builder, which turns Shadowrun PDFs you own into a Foundry VTT compendium.%n%nNo game content is included. You supply the books.
