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
SetupIconFile=wizard\app.ico

; Wizard artwork. Several sizes each so Windows picks one per display scaling
; rather than stretching a single 100% image, which on a 200% display looks
; exactly as bad as it sounds. BMP rather than PNG: PNG wizard images need
; Inno 6.3+, and BMP works everywhere — the figure is composited onto the
; app's own panel colour first, since BMP carries no alpha.
WizardImageFile=wizard\wizard-164x314.bmp,wizard\wizard-192x386.bmp,wizard\wizard-256x482.bmp,wizard\wizard-328x628.bmp
WizardImageStretch=yes
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

[Files]
; the sidebar figure, unpacked before the wizard is drawn so it can be loaded
; in InitializeWizard
Source: "wizard\sidebar-*.bmp"; Flags: dontcopy

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

[Code]
{ The runner stands full height down the LEFT of every page, and the wizard's
  own controls are moved right to make room.

  Inno only draws WizardImageFile on the welcome and finished pages, and only
  inside a fixed box. To have the figure present throughout, a TBitmapImage is
  parented to the form and every other control is shifted by its width.

  "Transparent" here means composited onto the wizard's own white: a
  TBitmapImage created in code has no alpha channel, so a PNG cutout would
  arrive with a black box behind it. Matching the background is the honest way
  to get the same result.                                                     }

var
  Runner: TBitmapImage;

function SidebarFile(): String;
var
  W: Integer;
begin
  { pick the render closest to the display scaling, then let it scale DOWN —
    enlarging a bitmap softens it, reducing one does not }
  W := ScaleY(420);
  if W >= 780 then Result := 'sidebar-686x840.bmp'
  else if W >= 580 then Result := 'sidebar-516x630.bmp'
  else if W >= 470 then Result := 'sidebar-413x504.bmp'
  else Result := 'sidebar-345x420.bmp';
end;

procedure ShiftRight(C: TControl; By: Integer);
begin
  if C <> nil then
  begin
    C.Left := C.Left + By;
    C.Width := C.Width - By;
  end;
end;

procedure InitializeWizard();
var
  ArtW, ArtH, MaxW: Integer;
  F: String;
begin
  F := SidebarFile();
  ExtractTemporaryFile(F);

  { The panel is sized FROM the bitmap so the figure fills the height with
    nothing cropped and no dead space. A fixed width cannot do both: too narrow
    and the figure is squeezed and clipped, too wide and it floats in a column
    of white. Capped at a third of the screen so it cannot swallow the window
    on a small display. }
  Runner := TBitmapImage.Create(WizardForm);
  Runner.Parent := WizardForm;
  Runner.Bitmap.LoadFromFile(ExpandConstant('{tmp}\') + F);
  Runner.Stretch := True;

  { width follows the bitmap's own aspect at the wizard's height, so the figure
    fills the height without being distorted or cropped }
  ArtH := WizardForm.ClientHeight;
  ArtW := (Runner.Bitmap.Width * ArtH) div Runner.Bitmap.Height;
  MaxW := (WizardForm.Width * 2) div 5;
  if ArtW > MaxW then
  begin
    ArtW := MaxW;
    ArtH := (Runner.Bitmap.Height * ArtW) div Runner.Bitmap.Width;
  end;

  Runner.Left := 0;
  Runner.Top := WizardForm.ClientHeight - ArtH;
  Runner.Width := ArtW;
  Runner.Height := ArtH;
  Runner.Anchors := [akLeft, akBottom];

  { widen the window so the figure is added BESIDE the content rather than
    eating into it, then move everything the wizard draws right past it }
  WizardForm.Width := WizardForm.Width + ArtW;
  WizardForm.Left := WizardForm.Left - (ArtW div 2);
  if WizardForm.Left < 0 then WizardForm.Left := 0;


  ShiftRight(WizardForm.OuterNotebook, ArtW);
  ShiftRight(WizardForm.InnerNotebook, ArtW);
  ShiftRight(WizardForm.Bevel, ArtW);
  ShiftRight(WizardForm.MainPanel, ArtW);

  { the welcome and finished pages carry their own image; it is redundant now }
  WizardForm.WizardBitmapImage.Visible := False;
  WizardForm.WizardBitmapImage2.Visible := False;
  { Inno's own box-and-disc mark, top right. Removing the
    WizardSmallImageFile line does not remove the image -- it falls back
    to the built-in one. It has to be hidden. }
  WizardForm.WizardSmallBitmapImage.Visible := False;

  Runner.SendToBack();
end;
