#define AppName "AKIRA"
#define AppVersion "16.3.2"

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
OutputBaseFilename=AKIRA_16_3_2_INSTALADOR_COMPLETO
UninstallDisplayIcon={app}\AKIRA.exe
SetupIconFile=..\assets\akira.ico
WizardImageFile=..\assets\installer_left.bmp
WizardSmallImageFile=..\assets\installer_small.bmp
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
DisableProgramGroupPage=yes
DisableReadyMemo=yes
DisableWelcomePage=no
UsePreviousAppDir=no
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
VersionInfoVersion=16.3.2.0
VersionInfoDescription=AKIRA - Instalador de Windows

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "..\native\AKIRA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Downloaded by Inno Setup with SHA-256 verification BEFORE any files are installed.
Source: "{tmp}\Qwen3-4B-Q4_K_M.gguf"; DestDir: "{app}\local_ai\models"; Flags: external ignoreversion deleteafterinstall

[Icons]
Name: "{autoprograms}\AKIRA"; Filename: "{app}\AKIRA.exe"; IconFilename: "{app}\AKIRA.exe"
Name: "{autodesktop}\AKIRA"; Filename: "{app}\AKIRA.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos"; Flags: checkedonce

[Run]
Filename: "{app}\AKIRA.exe"; Description: "Iniciar AKIRA"; Flags: postinstall nowait skipifsilent

[Code]
var
  AIPage: TDownloadWizardPage;
  EraseUserData: Boolean;
  CancelledDuringDownload: Boolean;

function AIProgress(const Url, FileName: String;
  const Progress, ProgressMax: Int64): Boolean;
begin
  AIPage.Msg1Label.Caption := 'Preparando la inteligencia artificial de AKIRA';
  Result := True;
end;

procedure InitializeWizard();
begin
  AIPage := CreateDownloadPage(
    'Preparando AKIRA', 'El instalador trabaja en segundo plano. Puedes cancelar.',
    @AIProgress);
  AIPage.ShowBaseNameInsteadOfUrl := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpReady then
  begin
    AIPage.Clear;
    AIPage.Add(
      'https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf',
      'Qwen3-4B-Q4_K_M.gguf',
      '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5');
    CancelledDuringDownload := False;
    AIPage.Show;
    try
      try
        AIPage.Download;
      except
        DeleteFile(ExpandConstant('{tmp}\Qwen3-4B-Q4_K_M.gguf'));
        if AIPage.AbortedByUser then
        begin
          Result := False;
          CancelledDuringDownload := True;
        end
        else
        begin
          MsgBox('No se pudo preparar la IA local. No se instalará una versión incompleta.', mbCriticalError, MB_OK);
          Result := False;
        end;
      end;
    finally
      AIPage.Hide;
    end;
    if CancelledDuringDownload then
      WizardForm.Close;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not FileExists(ExpandConstant('{app}\AKIRA.exe')) then
      RaiseException('No se encontró AKIRA.exe después de instalar.');
    if not FileExists(ExpandConstant('{app}\local_ai\bin\llama-server.exe')) then
      RaiseException('No se encontró el motor local llama-server.exe.');
    if not FileExists(ExpandConstant('{app}\local_ai\models\Qwen3-4B-Q4_K_M.gguf')) then
      RaiseException('No se encontró el modelo local Qwen3-4B.');
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  EraseUserData := (MsgBox('¿Borrar también chats, ajustes e historial local de AKIRA? Esta acción no se puede deshacer.', mbConfirmation, MB_YESNO) = IDYES);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and EraseUserData then
    DelTree(ExpandConstant('{localappdata}\AKIRA'), True, True, True);
end;
