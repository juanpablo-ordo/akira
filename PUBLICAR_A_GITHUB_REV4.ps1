# AKIRA: publica únicamente el código REV4 en una rama aislada.
# NO modifica main. NO ejecuta trading. No necesita contraseñas en el script.
param(
  [string]$Branch = 'akira-r8-studio-rev4-20261016'
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
  $script:GitExe = $tryPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if (!$script:GitExe) {
    throw 'No se encontró Git para Windows. Instala Git o GitHub Desktop con Git accesible y vuelve a ejecutar.'
  }
}

$required = @('Akira.py', 'studio_theme.py','akira_studio.py', 'operation_health.py', 'activity_watchdog.py',
              'REQUISITOS_232_ESTADO.csv', '.github\workflows\build-windows.yml')
foreach ($name in $required) {
  if (!(Test-Path -LiteralPath (Join-Path $Root $name))) { throw "Paquete incompleto: falta $name" }
}

$TempRoot = Join-Path $env:TEMP ('AKIRA_REV4_PUBLICACION_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
$RepoDir = Join-Path $TempRoot 'akira'
New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null
Write-Host 'Se usará una carpeta temporal para no alterar tus archivos locales:' $TempRoot
Write-Host 'Clonando GitHub con el inicio de sesión de Git que tengas configurado...'
RunGit -CmdArgs @('clone','--depth','1',$RepoUrl,$RepoDir)
RunGit -CmdArgs @('-C',$RepoDir,'switch','-c',$Branch)
# Borrar SOLO el árbol de trabajo del CLON TEMPORAL para importar el código completo.
# Nunca ejecuta git rm en tu carpeta original ni en main remoto.
RunGit -CmdArgs @('-C',$RepoDir,'rm','-r','-q','--ignore-unmatch','.')
$RoboLog = Join-Path $TempRoot 'robocopy.log'
$blockedDirs = @('.git', '__pycache__', '.pytest_cache', 'state','logs','exports','native','dist','build', '.venv', 'venv')
$blockedFiles = @('*.sqlite','*.sqlite3','*.db','*.key','*.pem','*.gguf','*.safetensors','*.env','*.env.*','AKIRA_SECRETS.json','*credentials*','*.log','*.exe','*.pyc','*.pyo')
& robocopy.exe $Root $RepoDir /E /NFL /NDL /NJH /NJS /NP /XD $blockedDirs /XF $blockedFiles | Out-File -Encoding utf8 $RoboLog
if ($LASTEXITCODE -gt 7) { throw "Error copiando código. Revisa $RoboLog" }
RunGit -CmdArgs @('-C',$RepoDir,'add','-A')
$staged = @(& $script:GitExe -C $RepoDir diff --cached --name-only)
if ($LASTEXITCODE -ne 0 -or $staged.Count -lt 50) { throw 'Cambios insuficientes: no se publicará un paquete incompleto.' }
# No confundir el módulo público akira_secrets.py (código para cifrar y leer claves)
# con AKIRA_SECRETS.json (archivo PRIVADO con valores de las claves).
# Powershell -match es insensible a mayúsculas: AKIRA_SECRETS sin extensión
# bloqueaba equivocadamente akira_secrets.py y hacía imposible publicar.
$secretPaths = @($staged | Where-Object {
  $stagedPath = ($_ -replace '\\', '/')
  ($stagedPath -match '(^|/)(state|logs|exports)/') -or
  ($stagedPath -match '(^|/)(AKIRA_SECRETS\.json|\.env(\.[^/]*)?|[^/]*credentials[^/]*|[^/]*\.sqlite3?|[^/]*\.db|[^/]*\.key|[^/]*\.pem|[^/]*\.gguf)$')
})
if ('akira_secrets.py' -notin $staged) {
  throw 'Paquete incompleto: falta akira_secrets.py, módulo requerido para gestión segura de claves.'
}
if ($secretPaths.Count -gt 0) { throw "Se encontraron rutas privadas: $($secretPaths -join ', '). Detenido sin publicar." }
RunGit -CmdArgs @('-C',$RepoDir,'diff','--cached','--check')
Write-Host "Archivos modificados ($($staged.Count)). Rama: $Branch"
$author = (& $script:GitExe -C $RepoDir config user.name)
if (!$author) { throw 'Git no tiene configurado user.name; configúralo en GitHub Desktop/Git antes de publicar.' }
$email = (& $script:GitExe -C $RepoDir config user.email)
if (!$email) { throw 'Git no tiene configurado user.email; configúralo antes de publicar.' }
RunGit -CmdArgs @('-C',$RepoDir,'commit','-m','AKIRA 16.3.5 R8 Studio Rev4: código fuente y CI Windows (sin datos de cuentas)')
Write-Host 'Subiendo rama a GitHub. Puede solicitar inicio de sesión.'
RunGit -CmdArgs @('-C',$RepoDir,'push','--set-upstream','origin',$Branch)
Write-Host ''
Write-Host 'Rama publicada. CI Windows se inicia con el push; resultados en:'
Write-Host 'https://github.com/juanpablo-ordo/akira/actions'
Write-Host 'Crear/revisar pull request (NO fusionar hasta pasar las pruebas):'
Write-Host ('https://github.com/juanpablo-ordo/akira/compare/main...' + $Branch + '?expand=1')
Write-Host 'Conserva las operaciones reales en modo OBSERVE hasta probar MT5 demo.'
