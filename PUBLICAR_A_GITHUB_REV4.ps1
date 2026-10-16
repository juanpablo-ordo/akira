# AKIRA: publica únicamente el código REV4 en una rama aislada.
# NO modifica main. NO ejecuta trading. No necesita contraseñas en el script.
param(
  [string]$Branch = 'akira-r8-studio-rev4-20261016'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoUrl = 'https://github.com/juanpablo-ordo/akira.git'
# Branch lease prevents this whole source package from overwriting someone else's changes.
$ExpectedHead = 'b040778873006bd6b50da61968eec015cb39fe85'

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
              'REQUISITOS_232_ESTADO.csv', '.github\workflows\build-windows.yml', 'akira_secrets.py')
foreach ($name in $required) {
  if (!(Test-Path -LiteralPath (Join-Path $Root $name))) { throw "Paquete incompleto: falta $name" }
}

$TempRoot = Join-Path $env:TEMP ('AKIRA_REV4_PUBLICACION_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
$RepoDir = Join-Path $TempRoot 'akira'
New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null
Write-Host 'Se usará una carpeta temporal para no alterar tus archivos locales:' $TempRoot
Write-Host 'Clonando GitHub con el inicio de sesión de Git que tengas configurado...'
RunGit -CmdArgs @('clone','--depth','1','--single-branch','--branch',$Branch,$RepoUrl,$RepoDir)
$remoteHead = (& $script:GitExe -C $RepoDir rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $remoteHead -ne $ExpectedHead) {
  throw "La rama cambió desde que se preparó el paquete. Esperado: $ExpectedHead; remoto: $remoteHead. Se detuvo para no sobrescribir otros cambios."
}
# Borrar SOLO el árbol de trabajo del CLON TEMPORAL para importar el código completo.
# Nunca ejecuta git rm en tu carpeta original ni en main remoto.
RunGit -CmdArgs @('-C',$RepoDir,'rm','-r','-q','--ignore-unmatch','.')
$RoboLog = Join-Path $TempRoot 'robocopy.log'
$blockedDirs = @('.git', '__pycache__', '.pytest_cache', 'state','logs','exports','native','dist','build', '.venv', 'venv')
$blockedFiles = @('*.sqlite','*.sqlite3','*.db','*.key','*.pem','*.gguf','*.safetensors','*.env','*.env.*','AKIRA_SECRETS.json','*credentials*','*.log','*.exe','*.pyc','*.pyo','*.patch')
& robocopy.exe $Root $RepoDir /E /NFL /NDL /NJH /NJS /NP /XD $blockedDirs /XF $blockedFiles | Out-File -Encoding utf8 $RoboLog
if ($LASTEXITCODE -gt 7) { throw "Error copiando código. Revisa $RoboLog" }
RunGit -CmdArgs @('-C',$RepoDir,'add','-A')
$staged = @(& $script:GitExe -C $RepoDir diff --cached --name-only)
if ($LASTEXITCODE -ne 0 -or $staged.Count -lt 1) { throw 'La rama ya coincide con este paquete o no hay cambios. No se necesita otra publicación.' }
# No confundir el módulo público akira_secrets.py (código para cifrar y leer claves)
# con AKIRA_SECRETS.json (archivo PRIVADO con valores de las claves).
# Powershell -match es insensible a mayúsculas: AKIRA_SECRETS sin extensión
# bloqueaba equivocadamente akira_secrets.py y hacía imposible publicar.
$secretPaths = @($staged | Where-Object {
  $stagedPath = ($_ -replace '\\', '/')
  ($stagedPath -match '(^|/)(state|logs|exports)/') -or
  ($stagedPath -match '(^|/)(AKIRA_SECRETS\.json|\.env(\.[^/]*)?|[^/]*credentials[^/]*|[^/]*\.sqlite3?|[^/]*\.db|[^/]*\.key|[^/]*\.pem|[^/]*\.gguf)$')
})
# Comprueba el modulo dentro del clon DESPUES de copiar y hacer git add.
# No uses $staged: Git omite archivos rastreados que no cambiaron,
# aunque esten presentes tanto en el ZIP como en el repositorio.
$modulePath = Join-Path $RepoDir 'akira_secrets.py'
if (!(Test-Path -LiteralPath $modulePath -PathType Leaf)) {
  throw 'Paquete incompleto: falta akira_secrets.py en el clon preparado. No se publico nada.'
}
& $script:GitExe -C $RepoDir ls-files --error-unmatch -- akira_secrets.py | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw 'akira_secrets.py existe, pero Git no lo rastrea en el paquete. No se publico nada.'
}
if ($secretPaths.Count -gt 0) { throw "Se encontraron rutas privadas: $($secretPaths -join ', '). Detenido sin publicar." }
# Core.whitespace=cr-at-eol accepts Windows CRLF as a line ending, but still
# REJECTS real trailing whitespace, new empty lines at EOF, and conflict markers.
# Do not confuse CRLF with a security or code-quality violation.
$checkArgs = @('-c','core.whitespace=cr-at-eol','-C',$RepoDir,'diff','--cached','--check')
$checkLines = @(& $script:GitExe @checkArgs 2>&1)
$checkExitCode = $LASTEXITCODE
if ($checkExitCode -ne 0) {
  $checkDetail = ($checkLines | Out-String).Trim()
  if (!$checkDetail) { $checkDetail = 'Git no devolvio detalles.' }
  throw "Los archivos preparados tienen problemas de formato (git diff --check, salida $checkExitCode):`n$checkDetail`nNo se publico nada."
}
Write-Host "Archivos modificados ($($staged.Count)). Rama: $Branch"
$author = (& $script:GitExe -C $RepoDir config user.name)
if (!$author) { throw 'Git no tiene configurado user.name; configúralo en GitHub Desktop/Git antes de publicar.' }
$email = (& $script:GitExe -C $RepoDir config user.email)
if (!$email) { throw 'Git no tiene configurado user.email; configúralo antes de publicar.' }
RunGit -CmdArgs @('-C',$RepoDir,'commit','-m','AKIRA R8 Studio Rev4: layout adaptable y charts visibles en Windows CI')
Write-Host 'Actualizando SOLO la rama Rev4 en GitHub, sin forzar cambios.'
RunGit -CmdArgs @('-C',$RepoDir,'push','origin',('HEAD:refs/heads/' + $Branch))
Write-Host ''
Write-Host 'Rama actualizada. CI Windows se inicia con el push; resultados en:'
Write-Host 'https://github.com/juanpablo-ordo/akira/actions'
Write-Host 'Crear/revisar pull request (NO fusionar hasta pasar las pruebas):'
Write-Host ('https://github.com/juanpablo-ordo/akira/compare/main...' + $Branch + '?expand=1')
Write-Host 'Conserva las operaciones reales en modo OBSERVE hasta probar MT5 demo.'
