#define AppName "AKIRA"
#define AppVersion "16.5.0"
#define LocalAIModelPath GetEnv("AKIRA_MODEL_PATH")
#define LocalAIModelSHA256 "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5"
#if LocalAIModelPath == ""
  #error AKIRA_MODEL_PATH must point to the verified GGUF before compiling the complete installer.
#endif

[Setup]
AppId={{82CE3E25-3E61-4978-9E4F-83524975B9AA}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=AKIRA
DefaultDirName={localappdata}\Programs\AKIRA
DefaultGroupName=AKIRA
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist_installer
OutputBaseFilename=AKIRA_16_5_0_STUDIO_REV15_IA_INCLUIDA
UninstallDisplayIcon={app}\AKIRA.exe
SetupIconFile=..\assets\akira.ico
WizardImageFile=..\assets\installer_left.bmp
WizardSmallImageFile=..\assets\installer_small.bmp
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
DiskSpanning=no
DisableProgramGroupPage=yes
DisableReadyMemo=yes
DisableWelcomePage=no
UsePreviousAppDir=no
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
VersionInfoVersion=16.5.0.0
VersionInfoDescription=AKIRA - Instalador de Windows

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "..\native\AKIRA\*"; DestDir: "{app}"; Excludes: "local_ai\models\*"; Flags: ignoreversion recursesubdirs createallsubdirs
; The compiler verifies and embeds the same model that passed the Windows chat test.
; Keep the installed model: deleteafterinstall would remove the AI immediately.
Source: "{#LocalAIModelPath}"; DestDir: "{app}\local_ai\models"; DestName: "Qwen3-4B-Q4_K_M.gguf"; Flags: ignoreversion nocompression; Hash: "{#LocalAIModelSHA256}"

[Icons]
Name: "{autoprograms}\AKIRA"; Filename: "{app}\AKIRA.exe"; IconFilename: "{app}\AKIRA.exe"
Name: "{autodesktop}\AKIRA"; Filename: "{app}\AKIRA.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos"; Flags: checkedonce

[Run]
Filename: "{app}\AKIRA.exe"; Description: "Iniciar AKIRA"; Flags: postinstall nowait skipifsilent

[Code]
const
  LocalAIModelSHA256 = '{#LocalAIModelSHA256}';

var
  EraseUserData: Boolean;
  UninstallCloseCode: Integer;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not FileExists(ExpandConstant('{app}\bin\deno.exe')) then
      RaiseException('No se encontró el componente YouTube de AKIRA.');
    if not FileExists(ExpandConstant('{app}\AKIRA.exe')) then
      RaiseException('No se encontró AKIRA.exe después de instalar.');
    if not FileExists(ExpandConstant('{app}\local_ai\bin\llama-server.exe')) then
      RaiseException('No se encontró el motor de IA local de AKIRA.');
    if not FileExists(ExpandConstant('{app}\local_ai\cpu\llama-server.exe')) then
      RaiseException('No se encontró el motor de IA para CPU de AKIRA.');
    if not FileExists(ExpandConstant('{app}\local_ai\models\Qwen3-4B-Q4_K_M.gguf')) then
      RaiseException('No se encontró la inteligencia artificial incluida en el instalador.');
    Log('Verificando la integridad de la IA local instalada.');
    if Lowercase(GetSHA256OfFile(ExpandConstant('{app}\local_ai\models\Qwen3-4B-Q4_K_M.gguf'))) <> LocalAIModelSHA256 then
      RaiseException('La IA local instalada está incompleta o dañada. Vuelve a descargar el instalador completo.');
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  if FileExists(ExpandConstant('{app}\AKIRA.exe')) then
    Exec(ExpandConstant('{app}\AKIRA.exe'), '--prepare-uninstall', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, UninstallCloseCode);
  EraseUserData := (MsgBox('¿Borrar también chats, ajustes e historial local de AKIRA? Esta acción no se puede deshacer.', mbConfirmation, MB_YESNO) = IDYES);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and EraseUserData then
    DelTree(ExpandConstant('{localappdata}\AKIRA'), True, True, True);
end;
