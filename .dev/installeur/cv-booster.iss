; =====================================================================
;  Installer CV Booster.exe : une vraie installation Windows, comme Spotify ou Discord.
;  Compilé par .dev/construire_installeur.py (qui prépare d'abord staging/). Inno Setup 6.
;
;  Programme : %LOCALAPPDATA%\Programs\CV Booster   (sans droits administrateur)
;  Données   : Documents\CV Booster                 (ressources, CV, agents et Skills ; jamais supprimées)
;  Composants système (Claude Code, Git, moteur PDF) : installés en silence par prerequis.ps1.
;
;  Paramètres de test (ligne de commande) :
;    /DONNEES="C:\...\dossier"  autre dossier de données (sur le PC de dev, Documents\CV Booster = le projet !)
;    /SANSPREREQUIS             ne lance pas prerequis.ps1
;    /RELANCER                  rouvre CV Booster à la fin (mise à jour lancée depuis l'appli, en /SILENT)
;    + les options standard d'Inno : /DIR="...", /VERYSILENT, /SUPPRESSMSGBOXES, /LOG="..."
; =====================================================================

#define AppNom "CV Booster"
#ifndef AppVersion
  #define AppVersion "1.0.0"   ; normalement fourni par construire_installeur.py (/DAppVersion=…)
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
; images aux couleurs de l'appli (fabriquées par images.ps1), une par mise à l'échelle d'écran
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
fr.WelcomeLabel2=CV Booster va être installé sur ton ordinateur.%n%nTout ce qu'il faut est inclus : il n'y a rien d'autre à installer. Compte quelques minutes la première fois.
fr.ClickNext=Clique sur « Installer » pour commencer.
fr.ButtonNext=&Installer
fr.FinishedHeadingLabel=CV Booster est prêt
fr.FinishedLabelNoIcons=CV Booster est installé.
fr.FinishedLabel=CV Booster est installé. Tu le retrouves dans le menu Démarrer et sur le Bureau.%n%nTes documents et tes CV seront rangés dans Documents\CV Booster.
fr.ClickFinish=Clique sur « Terminer ».

[InstallDelete]
; mise à jour : les agents/Skills d'origine et les caches sont remplacés proprement
Type: filesandordirs; Name: "{app}\projet"
Type: filesandordirs; Name: "{app}\__pycache__"

[Files]
Source: "staging\*"; DestDir: "{app}"; Excludes: "Guide CV Booster.pdf"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "staging\Guide CV Booster.pdf"; DestDir: "{code:Donnees}"; Flags: ignoreversion uninsneveruninstall skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\{#AppNom}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\lancer.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\icone.ico"; AppUserModelID: "CVBooster.App"; Comment: "Améliore ton CV"
Name: "{autodesktop}\{#AppNom}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\lancer.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\icone.ico"; AppUserModelID: "CVBooster.App"; Comment: "Améliore ton CV"

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\lancer.pyw"""; WorkingDir: "{app}"; Description: "Lancer CV Booster"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; tout le dossier du programme (caches, config.json…). Les données, dans Documents, ne sont jamais touchées.
Type: filesandordirs; Name: "{app}"

[Code]
// Interrupteur « /NOM » sur la ligne de commande (la constante param ne lit que la forme /NOM=valeur)
function Commutateur(Nom: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/' + Nom) = 0 then
      Result := True;
end;

{ Dossier des données déjà choisi par une installation précédente (config.json), sinon '' }
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
    Result := DonneesExistantes();   { mise à jour : on garde le même dossier }
  if Result = '' then
    Result := ExpandConstant('{userdocs}\{#AppNom}');
end;

function PowerShell(): String;
begin
  Result := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
end;

{ Ferme CV Booster s'il tourne (fenêtre et serveur : les pythonw.exe du dossier du programme). }
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
  { mise à jour lancée depuis l'appli : on la rouvre à la fin }
  if (CurStep = ssDone) and Commutateur('RELANCER') then
    ExecAsOriginalUser(ExpandConstant('{app}\python\pythonw.exe'), '"' + ExpandConstant('{app}\lancer.pyw') + '"',
                       ExpandConstant('{app}'), SW_SHOWNORMAL, ewNoWait, Code);
  if CurStep <> ssPostInstall then
    exit;
  { 1. où sont les données : lu par lancer.pyw au démarrage }
  SetArrayLength(Lignes, 1);
  Lignes[0] := '{"donnees": "' + EnJson(Donnees('')) + '", "installe": true}';
  SaveStringsToUTF8File(ExpandConstant('{app}\config.json'), Lignes, False);
  { 2. composants système, en silence (fenêtre cachée) }
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
    MsgBox('CV Booster a été désinstallé.' #13#10#13#10 + 'Tes documents et tes CV sont conservés dans Documents\CV Booster.', mbInformation, MB_OK);
end;
