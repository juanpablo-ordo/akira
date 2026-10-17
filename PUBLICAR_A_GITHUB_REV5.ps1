# AKIRA: publica únicamente el código REV5 en una rama aislada.
# NO modifica main. NO ejecuta trading. No necesita contraseñas en el script.
param(
  [string]$Branch = 'akira-studio-rev5-20261016'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoUrl = 'https://github.com/juanpablo-ordo/akira.git'

function RunGit {
  param([string[]]$CmdArgs)
  & $script:GitExe @CmdArgs
  if ($LASTEXITCODE -ne 0) { throw "Git falló ($LASTEXITCODE): $($CmdArgs -join ' ')" }
}

$gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
if ($null -ne $gitCommand) { $script:GitExe = $gitCommand.Source }
else {
  $tryPaths = @(
    (Join-Path $env:ProgramFiles 'Git\cmd\git.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Git\cmd\git.exe')
  )
  $desktopGit = Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'GitHubDesktop\app-*\resources\app\git\cmd\git.exe') -ErrorAction SilentlyContinue | Select-Object -Last 1
  if ($desktopGit) { $tryPaths += $desktopGit.FullName }
  $script:GitExe = $tryPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if (!$script:GitExe) {
    throw 'No se encontró Git para Windows. Instala Git o GitHub Desktop con Git accesible y vuelve a ejecutar.'
  }
}

$required = @('Akira.py', 'desktop_qt.py','studio_controller.py','studio_settings_qt.py','studio_background.py','sprite_recognition.py', 'studio_theme.py','akira_studio.py', 'operation_health.py', 'activity_watchdog.py',
              'REQUISITOS_232_ESTADO.csv', '.github\workflows\build-windows.yml')
foreach ($name in $required) {
  if (!(Test-Path -LiteralPath (Join-Path $Root $name))) { throw "Paquete incompleto: falta $name" }
}

$TempRoot = Join-Path $env:TEMP ('AKIRA_REV5_PUBLICACION_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
$RepoDir = Join-Path $TempRoot 'akira'
New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null
Write-Host 'Se usará una carpeta temporal para no alterar tus archivos locales:' $TempRoot
Write-Host 'Clonando GitHub con el inicio de sesión de Git que tengas configurado...'
$remoteBranch = @(& $script:GitExe ls-remote --heads $RepoUrl ('refs/heads/' + $Branch))
if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprobar la rama remota. No se publicó nada.' }
if ($remoteBranch.Count -gt 0) {
  RunGit -CmdArgs @('clone','--depth','1','--branch',$Branch,$RepoUrl,$RepoDir)
} else {
  RunGit -CmdArgs @('clone','--depth','1',$RepoUrl,$RepoDir)
  RunGit -CmdArgs @('-C',$RepoDir,'switch','-c',$Branch)
}
# Borrar SOLO el árbol de trabajo del CLON TEMPORAL para importar el código completo.
# Nunca ejecuta git rm en tu carpeta original ni en main remoto.
RunGit -CmdArgs @('-C',$RepoDir,'rm','-r','-q','--ignore-unmatch','.')
$RoboLog = Join-Path $TempRoot 'robocopy.log'
$blockedDirs = @('.git', '__pycache__', '.pytest_cache', 'state','logs','exports','studio','native','dist','dist_installer','diagnostics','build', '.venv', 'venv')
$blockedFiles = @('*.sqlite','*.sqlite3','*.db','*.key','*.pem','*.gguf','*.safetensors','*.env','*.log','*.exe','*.pyc','*.pyo')
& robocopy.exe $Root $RepoDir /E /NFL /NDL /NJH /NJS /NP /XD $blockedDirs /XF $blockedFiles | Out-File -Encoding utf8 $RoboLog
if ($LASTEXITCODE -gt 7) { throw "Error copiando código. Revisa $RoboLog" }
RunGit -CmdArgs @('-C',$RepoDir,'add','-A')
$staged = @(& $script:GitExe -C $RepoDir diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw 'No se pudo leer la lista de cambios.' }
$tracked = @(& $script:GitExe -C $RepoDir ls-files)
if ($LASTEXITCODE -ne 0 -or $tracked.Count -lt 50) { throw 'Árbol incompleto: no se publicará.' }
if ($staged.Count -eq 0) {
  Write-Host 'Este código ya está publicado en la rama indicada. No se creó otro commit.'
  Write-Host 'https://github.com/juanpablo-ordo/akira/actions'
  exit 0
}
$secretPaths = @($staged | Where-Object { $_ -match '(^state/|^logs/|^exports/|^studio/|\.env$|\.sqlite3?$|\.db$|(^|/)AKIRA_SECRETS\.json$|\.key$|\.pem$|\.gguf$)' })
if ($secretPaths.Count -gt 0) { throw "Se encontraron rutas privadas: $($secretPaths -join ', '). Detenido sin publicar." }
# Los avisos de espacios heredados no impiden compilar ni cambian el contenido.
# Se guardan para revisión; un fallo real de lectura sí detiene la publicación.
$WhitespaceLog = Join-Path $TempRoot 'espacios_revisar.txt'
& $script:GitExe -C $RepoDir diff --cached --check 2>&1 | Out-File -Encoding utf8 $WhitespaceLog
$WhitespaceExit = $LASTEXITCODE
if ($WhitespaceExit -notin @(0,2)) { throw "No se pudo revisar el diff ($WhitespaceExit): $WhitespaceLog" }
if ($WhitespaceExit -eq 2) { Write-Host "Avisos de espacios conservados en $WhitespaceLog. Se continúa con el código íntegro." }
Write-Host "Archivos modificados ($($staged.Count)). Rama: $Branch"
$author = (& $script:GitExe -C $RepoDir config user.name)
if (!$author) { throw 'Git no tiene configurado user.name; configúralo en GitHub Desktop/Git antes de publicar.' }
$email = (& $script:GitExe -C $RepoDir config user.email)
if (!$email) { throw 'Git no tiene configurado user.email; configúralo antes de publicar.' }
RunGit -CmdArgs @('-C',$RepoDir,'commit','-m','AKIRA Studio 16.4.0 Rev5: corregir entradas y comprobar IA local Windows 5')
Write-Host 'Subiendo rama a GitHub. Puede solicitar inicio de sesión.'
RunGit -CmdArgs @('-C',$RepoDir,'push','--set-upstream','origin',$Branch)
Write-Host ''
Write-Host 'Rama publicada. CI Windows se inicia con el push; resultados en:'
Write-Host 'https://github.com/juanpablo-ordo/akira/actions'
Write-Host 'Crear/revisar pull request (NO fusionar hasta pasar las pruebas):'
Write-Host ('https://github.com/juanpablo-ordo/akira/compare/main...' + $Branch + '?expand=1')
Write-Host 'Conserva las operaciones reales en modo OBSERVE hasta probar MT5 demo.'
