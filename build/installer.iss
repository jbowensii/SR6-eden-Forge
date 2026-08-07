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
  #define AppVersion "0.8.0"
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
; The review app: sources, the BUILT front end, and its runtime packages.
;
; dist\ and node_modules\ were both excluded here, which meant the installed
; "Review & correct" button started a server that died on
;   Cannot find package 'express'
; and, had it started, would have served no front end. Neither is optional:
; server/index.mjs does express.static(../dist).
Source: "..\site\*"; DestDir: "{app}\site"; \
    Flags: ignoreversion recursesubdirs; \
    Excludes: "node_modules\*,*.log"
; Production dependencies only — staged by build_release.py with
; `npm ci --omit=dev`. 17 MB, against 66 MB for the tree with vite and react's
; dev tooling in it, none of which runs on the user's machine.
Source: "work\site-deps\node_modules\*"; DestDir: "{app}\site\node_modules"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\NOTICE"; DestDir: "{app}"; Flags: ignoreversion
; The shortcuts point at THIS rather than at the executable's own resource.
; The exe does carry the icon, but earlier builds did not, and the Windows
; shell caches "this path has no icon" per path — so a shortcut to the exe kept
; drawing the generic file glyph long after the icon was fixed. A separate .ico
; is a different cache key, and it renders immediately.
Source: "wizard\app.ico"; DestDir: "{app}"; Flags: ignoreversion

[Files]
; the sidebar figure, unpacked before the wizard is drawn so it can be loaded
; in InitializeWizard
Source: "wizard\sidebar-*.bmp"; Flags: dontcopy

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\SR6CatalogBuilder.exe"; \
    IconFilename: "{app}\app.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\SR6CatalogBuilder.exe"; \
    IconFilename: "{app}\app.ico"; Tasks: desktopicon

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
{ The runner stands down the LEFT of every page, his boots level with the
  bottom of the page's content box, and the wizard's own controls are moved
  right to make room for him.

  Inno only draws WizardImageFile on the welcome and finished pages, and only
  inside a fixed box. To have the figure present throughout, a TBitmapImage is
  parented to the form itself and every other control is shifted by its width.

  "Transparent" here means composited onto the wizard's own white: a
  TBitmapImage created in code has no alpha channel, so a PNG cutout would
  arrive with a black box behind it. Matching the background is the honest way
  to get the same result.                                                     }

var
  Runner, Backing: TBitmapImage;

procedure StopOurReviewServer();
var
  Code: Integer;
begin
  { The review app is a background node.exe with no window and no tray icon.
    It outlives the app that started it, keeps a LevelDB binding open under
    site\node_modules, and setup then fails halfway through with

      DeleteFile failed; code 5.  Access is denied.

    on classic-level.node. There is nothing for the user to close, because
    there is nothing on screen to close.

    So setup stops it itself. Matched on the COMMAND LINE, never on the name:
    a developer machine runs dozens of node.exe processes and Foundry is one of
    them. Only a node running OUR server script is touched, and -EA 0 keeps a
    failure here from stopping the install. }
  Exec(ExpandConstant('{cmd}'),
       '/C powershell -NoProfile -WindowStyle Hidden -Command "' +
       'Get-CimInstance Win32_Process | Where-Object { $_.Name -eq ''node.exe''' +
       ' -and $_.CommandLine -like ''*site*server*index.mjs*'' } | ' +
       'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA 0 }"',
       '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopOurReviewServer();
  Sleep(600);           { let Windows release the file handles }
  Result := '';         { never block the install over this }
end;

function SidebarFile(): String;
var
  W: Integer;
begin
  { pick the render closest to the display scaling, then let it scale DOWN --
    enlarging a bitmap softens it, reducing one does not }
  W := ScaleY(420);
  if W >= 780 then Result := 'sidebar-686x840.bmp'
  else if W >= 580 then Result := 'sidebar-516x630.bmp'
  else if W >= 470 then Result := 'sidebar-413x504.bmp'
  else Result := 'sidebar-345x420.bmp';
end;

function AbsTop(C: TControl): Integer;
var
  P: TControl;
begin
  { A control's Top is relative to its PARENT, and Inno nests the page controls
    several levels down (form -> notebook -> page -> control). Walking up to
    the form is what turns that into the y the figure has to line up with. }
  Result := 0;
  P := C;
  while (P <> nil) and (P <> WizardForm) do
  begin
    Result := Result + P.Top;
    P := P.Parent;
  end;
end;

procedure ShiftRight(C: TControl; By: Integer);
begin
  { Only controls parented DIRECTLY to the form. Inno nests some of these --
    shifting a parent and then its child moves the child twice, which is how
    the text ended up starting at roughly double the figure's width with a
    band of dead white between the two. }
  if (C <> nil) and (C.Parent = WizardForm) then
  begin
    C.Left := C.Left + By;
    C.Width := C.Width - By;
  end;
end;

procedure InitializeWizard();
var
  ArtW, ArtH, MaxW, Shift, Overlap, TextBottom, ColumnBottom: Integer;
  F: String;
begin
  F := SidebarFile();
  ExtractTemporaryFile(F);
  ExtractTemporaryFile('sidebar-bg.bmp');

  { Both anchors are READ from real controls rather than guessed at, so they
    hold at any display scaling: the bottom of the licence box, which the
    figure's boots line up with, and the rule above the buttons, which the
    white column stops at so the button strip keeps the form's own grey. }
  TextBottom := AbsTop(WizardForm.LicenseMemo) + WizardForm.LicenseMemo.Height;
  ColumnBottom := AbsTop(WizardForm.Bevel);

  { The white column the figure stands in.
    A TBitmapImage, NOT a TPanel: Inno's panels are theme-drawn, so assigning
    Color := clWhite is quietly ignored and the column stayed the form's grey
    above the figure's own white background -- which is the grey box that kept
    appearing in the top-left corner. A bitmap always paints what it is given. }
  Backing := TBitmapImage.Create(WizardForm);
  Backing.Parent := WizardForm;
  Backing.Bitmap.LoadFromFile(ExpandConstant('{tmp}\sidebar-bg.bmp'));
  Backing.Stretch := True;
  Backing.Left := 0;
  Backing.Top := 0;
  Backing.Height := ColumnBottom;

  Runner := TBitmapImage.Create(WizardForm);
  Runner.Parent := WizardForm;
  Runner.Bitmap.LoadFromFile(ExpandConstant('{tmp}\') + F);
  Runner.Stretch := True;

  { Width follows the bitmap's OWN aspect, so the figure is never stretched.
    Capped twice -- by a share of the window, and by the height available above
    the licence box -- and whichever bites first decides the other dimension. }
  ArtH := TextBottom;
  ArtW := (Runner.Bitmap.Width * ArtH) div Runner.Bitmap.Height;
  MaxW := (WizardForm.Width * 2) div 5;
  if ArtW > MaxW then
  begin
    ArtW := MaxW;
    ArtH := (Runner.Bitmap.Height * ArtW) div Runner.Bitmap.Width;
  end;

  Backing.Width := ArtW;

  Runner.Left := 0;
  Runner.Width := ArtW;
  Runner.Height := ArtH;
  Runner.Top := TextBottom - ArtH;     { boots level with the licence box }
  Runner.Anchors := [akLeft, akTop];

  { How far the wizard's own controls move over. Deliberately a little LESS
    than the figure's width, so he stands ON the page rather than in a column
    beside it. The overlap is taken out of the shift, not out of the page's own
    text inset, so what he covers is the empty left margin -- no label, no
    licence box and no radio button ends up underneath him. }
  Overlap := ScaleX(40);
  Shift := ArtW - Overlap;
  if Shift < 0 then Shift := 0;

  WizardForm.Width := WizardForm.Width + Shift;
  WizardForm.Left := WizardForm.Left - (Shift div 2);
  if WizardForm.Left < 0 then WizardForm.Left := 0;

  ShiftRight(WizardForm.OuterNotebook, Shift);
  ShiftRight(WizardForm.InnerNotebook, Shift);
  ShiftRight(WizardForm.Bevel, Shift);
  ShiftRight(WizardForm.MainPanel, Shift);

  { the welcome and finished pages carry their own copy of the figure; it is
    redundant once he is on every page }
  WizardForm.WizardBitmapImage.Visible := False;
  WizardForm.WizardBitmapImage2.Visible := False;
  { Inno's own box-and-disc mark, top right. Removing the WizardSmallImageFile
    line does not remove it -- it falls back to the built-in one. }
  WizardForm.WizardSmallBitmapImage.Visible := False;

  { white column behind everything, figure in front of everything }
  Backing.SendToBack();
  Runner.BringToFront();
end;
