; =====================================================================
;  Installer CV Booster.exe: a real Windows installer, like Spotify or Discord.
;  Built by .dev/construire_installeur.py (which prepares staging/ first). Inno Setup 6.
;
;  Program : %LOCALAPPDATA%\Programs\CV Booster   (no admin rights)
;  Data    : Documents\CV Booster                 (ressources, CV, agents and Skills; never deleted)
;  System components (Claude Code, Git, PDF engine): installed silently by prerequis.ps1.
;
;  Test parameters (command line):
;    /DONNEES="C:\...\dossier"  another data folder (on the dev PC, Documents\CV Booster = the project!)
;    /SANSPREREQUIS             skips prerequis.ps1
;    /RELANCER                  reopens CV Booster at the end (update started from the app, in /SILENT)
;    + Inno's standard options: /DIR="...", /VERYSILENT, /SUPPRESSMSGBOXES, /LOG="..."
; =====================================================================

#define AppNom "CV Booster"
#ifndef AppVersion
  #define AppVersion "1.0.0"   ; normally passed by construire_installeur.py (/DAppVersion=…)
#endif

[Setup]
AppId={{8C1F3A52-6B7E-4E1D-9A43-2F5C0B7D9E61}
AppName={#AppNom}
AppVersion={#AppVersion}
AppVerName={#AppNom}
AppPublisher={#AppNom}
DefaultDirName={autopf}\{#AppNom}
PrivilegesRequired=lowest
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableWelcomePage=no
WizardStyle=modern
; images in the app's colors (made by images.ps1), one per display scaling
WizardImageFile=panneau-164.bmp,panneau-192.bmp,panneau-246.bmp,panneau-273.bmp,panneau-328.bmp,panneau-410.bmp
WizardSmallImageFile=vignette-55.bmp,vignette-64.bmp,vignette-83.bmp,vignette-92.bmp,vignette-110.bmp,vignette-119.bmp,vignette-138.bmp
OutputDir=..\dist
OutputBaseFilename=Installer CV Booster
SetupIconFile=staging\icone.ico
UninstallDisplayIcon={app}\icone.ico
UninstallDisplayName={#AppNom}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=no

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Messages]
fr.WelcomeLabel1=Bienvenue dans CV Booster
fr.WelcomeLabel2=CV Booster va être installé sur votre ordinateur.%n%nTout ce qu'il faut est inclus : il n'y a rien d'autre à installer. Comptez quelques minutes la première fois.
fr.ClickNext=Cliquez sur « Installer » pour commencer.
fr.ButtonNext=&Installer
fr.FinishedHeadingLabel=CV Booster est prêt
fr.FinishedLabelNoIcons=CV Booster est installé.
fr.FinishedLabel=CV Booster est installé. Vous le retrouvez dans le menu Démarrer et sur le Bureau.%n%nVos documents et vos CV seront rangés dans Documents\CV Booster.
fr.ClickFinish=Cliquez sur « Terminer ».

[InstallDelete]
; update: the original agents/Skills and the caches are replaced cleanly
Type: filesandordirs; Name: "{app}\projet"
Type: filesandordirs; Name: "{app}\__pycache__"

[Files]
Source: "staging\*"; DestDir: "{app}"; Excludes: "Guide CV Booster.pdf"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "staging\Guide CV Booster.pdf"; DestDir: "{code:Donnees}"; Flags: ignoreversion uninsneveruninstall skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\{#AppNom}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\lancer.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\icone.ico"; AppUserModelID: "CVBooster.App"; Comment: "Améliorez votre CV"
Name: "{autodesktop}\{#AppNom}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\lancer.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\icone.ico"; AppUserModelID: "CVBooster.App"; Comment: "Améliorez votre CV"

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\lancer.pyw"""; WorkingDir: "{app}"; Description: "Lancer CV Booster"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; the whole program folder (caches, config.json…). The data, in Documents, is never touched.
Type: filesandordirs; Name: "{app}"

[Code]
// "/NOM" switch on the command line (the param constant only reads the /NOM=valeur form)
function Commutateur(Nom: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/' + Nom) = 0 then
      Result := True;
end;

{ Data folder already chosen by a previous install (config.json), otherwise '' }
function DonneesExistantes(): String;
var
  Texte: AnsiString;
  S: String;
  P: Integer;
begin
  Result := '';
  if not LoadStringFromFile(ExpandConstant('{app}\config.json'), Texte) then
    exit;
  S := UTF8Decode(Texte);
  P := Pos('"donnees":', S);
  if P = 0 then
    exit;
  S := Copy(S, P + 10, Length(S));
  P := Pos('"', S);
  S := Copy(S, P + 1, Length(S));
  P := Pos('"', S);
  Result := Copy(S, 1, P - 1);
  StringChangeEx(Result, '\\', '\', True);
end;

function Donnees(Param: String): String;
begin
  Result := ExpandConstant('{param:DONNEES|}');
  if Result = '' then
    Result := DonneesExistantes();   { update: keep the same folder }
  if Result = '' then
    Result := ExpandConstant('{userdocs}\{#AppNom}');
end;

function PowerShell(): String;
begin
  Result := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
end;

{ Close CV Booster if it is running (window and server: the pythonw.exe processes in the program folder). }
procedure FermerAppli(Dossier: String);
var
  Code: Integer;
begin
  if DirExists(Dossier) then
    Exec(PowerShell(), '-NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like ''' +
         Dossier + '\*'' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  FermerAppli(ExpandConstant('{app}'));
  Result := '';
end;

function EnJson(S: String): String;
begin
  Result := S;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Lignes: TArrayOfString;
  Code: Integer;
begin
  { update started from the app: reopen it at the end }
  if (CurStep = ssDone) and Commutateur('RELANCER') then
    ExecAsOriginalUser(ExpandConstant('{app}\python\pythonw.exe'), '"' + ExpandConstant('{app}\lancer.pyw') + '"',
                       ExpandConstant('{app}'), SW_SHOWNORMAL, ewNoWait, Code);
  if CurStep <> ssPostInstall then
    exit;
  { 1. where the data lives: read by lancer.pyw at startup }
  SetArrayLength(Lignes, 1);
  Lignes[0] := '{"donnees": "' + EnJson(Donnees('')) + '", "installe": true}';
  SaveStringsToUTF8File(ExpandConstant('{app}\config.json'), Lignes, False);
  { 2. system components, silently (hidden window) }
  if Commutateur('SANSPREREQUIS') then
    exit;
  WizardForm.StatusLabel.Caption := 'Installation des derniers composants (Claude, moteur PDF)… Cela peut prendre quelques minutes.';
  WizardForm.FilenameLabel.Caption := '';
  WizardForm.ProgressGauge.Style := npbstMarquee;
  Exec(PowerShell(), '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + ExpandConstant('{app}\prerequis.ps1') +
       '" -Donnees "' + Donnees('') + '" -App "' + ExpandConstant('{app}') + '"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  WizardForm.ProgressGauge.Style := npbstNormal;
end;

function InitializeUninstall(): Boolean;
begin
  FermerAppli(ExpandConstant('{app}'));
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    MsgBox('CV Booster a été désinstallé.' #13#10#13#10 + 'Vos documents et vos CV sont conservés dans Documents\CV Booster.', mbInformation, MB_OK);
end;
