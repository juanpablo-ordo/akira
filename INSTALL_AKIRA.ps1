$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$diagnosticBase=Join-Path $env:USERPROFILE 'Akira_Diagnostico_Instalacion'
$diagnostic=Join-Path $diagnosticBase ((Get-Date -Format 'yyyyMMdd_HHmmss')+'.'+[Guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $diagnostic -Force | Out-Null
$transcriptStarted=$false
try {
    Start-Transcript -Path (Join-Path $diagnostic 'INSTALACION_COMPLETA.log') -Force | Out-Null
    $transcriptStarted=$true
} catch { Write-Host 'No se pudo iniciar la transcripcion; las pruebas conservaran su propio registro.' }
$installPhase='Preparar instalación'
$installerMutex=$null
$mutexOwned=$false
$activated=$false
$installCommitted=$false
$expectedBuild='SIN_VERIFICAR'
$oldRoot=$null
$app=$null
try {
$packageManifest=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'VALIDACION_V12.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedBuild=[string]$packageManifest.build
if ([string]::IsNullOrWhiteSpace($expectedBuild)) { throw 'El manifiesto del paquete no identifica su versión.' }
$installerMutex=New-Object -TypeName System.Threading.Mutex -ArgumentList @($false,('Local\AkiraInstaller_'+$env:USERNAME))
try { $mutexOwned=$installerMutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $mutexOwned=$true }
if (-not $mutexOwned) { throw 'Ya hay otro instalador de Akira abierto. Termina esa instalación antes de iniciar otra.' }
$installPhase='Validar instalador y desinstalador independientes'
foreach ($scriptPath in @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1' -File)) {
    $psTokens=$null;$psErrors=$null
    [System.Management.Automation.Language.Parser]::ParseFile($scriptPath.FullName,[ref]$psTokens,[ref]$psErrors) | Out-Null
    if ($psErrors.Count -gt 0) { throw ('El componente '+$scriptPath.Name+' contiene errores de PowerShell: '+(($psErrors | ForEach-Object {$_.Message}) -join '; ')) }
}
$removalTestLog=Join-Path $diagnostic 'PRUEBA_DESINSTALADOR.json'
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'DESINSTALAR_AKIRA.ps1') -SelfTest *> $removalTestLog
if ($LASTEXITCODE -ne 0) { throw ('La autocomprobación del desinstalador falló: '+$removalTestLog+'. Se conserva la instalación anterior.') }
$legacyApp=Join-Path $env:LOCALAPPDATA 'Akira'
$installPhase='Comprobar que Akira está cerrada'
$akiraProcessPattern='(?i)(?:^|\s)(?:"[^"\r\n]*[\\/](?:Akira|Akira_FINAL_V[0-9]+|Akira_V[0-9]+)\.py"|[^\s"]*[\\/](?:Akira|Akira_FINAL_V[0-9]+|Akira_V[0-9]+)\.py|"?Akira\.py"?)(?=\s|$)'
function Get-AkiraRunning {
    @(Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -match '^python(w|[0-9]+([.][0-9]+)*)?[.]exe$' -and $_.CommandLine -match $akiraProcessPattern) -or ($_.Name -eq 'AKIRA.exe' -and $_.ExecutablePath -like (Join-Path $env:USERPROFILE '.akira_runtime\releases\*\native\AKIRA\AKIRA.exe'))
    })
}
function Stop-AkiraInstances {
    param([string]$Reason='continuar la instalación')
    $running=@(Get-AkiraRunning)
    if ($running.Count -eq 0) { return }
    $ids=(($running | ForEach-Object { [string]$_.ProcessId }) -join ', ')
    Write-Host ('Akira está abierta (PID '+$ids+'). El instalador cerrará únicamente esas instancias de Akira para '+$Reason+'...') -ForegroundColor Yellow
    foreach ($proc in $running) {
        try { Stop-Process -Id $proc.ProcessId -ErrorAction Stop }
        catch { Write-Host ('No se pudo cerrar normalmente el PID '+$proc.ProcessId+': '+$_.Exception.Message) -ForegroundColor Yellow }
    }
    $deadline=(Get-Date).AddSeconds(8)
    do {
        Start-Sleep -Milliseconds 250
        $remaining=@(Get-AkiraRunning)
    } while ($remaining.Count -gt 0 -and (Get-Date) -lt $deadline)
    if ($remaining.Count -gt 0) {
        Write-Host 'Akira no terminó a tiempo; cerrando únicamente las instancias detectadas de Akira de forma forzada...' -ForegroundColor Yellow
        foreach ($proc in $remaining) {
            try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop }
            catch { Write-Host ('No se pudo forzar el cierre del PID '+$proc.ProcessId+': '+$_.Exception.Message) -ForegroundColor Yellow }
        }
        Start-Sleep -Milliseconds 600
        $remaining=@(Get-AkiraRunning)
    }
    if ($remaining.Count -gt 0) {
        throw ('No pude cerrar automáticamente Akira. Procesos aún activos: '+(($remaining | ForEach-Object { [string]$_.ProcessId }) -join ', ')+'. Cierra solo esos procesos y vuelve a ejecutar el instalador; la instalación anterior se conserva.')
    }
    Write-Host 'Instancia anterior de Akira cerrada. Continuando sin dejar dos bots activos.' -ForegroundColor Green
}
Stop-AkiraInstances -Reason 'actualizar a AKIRA 16.3.5'
$installPhase='Preparar Python y dependencias'
Write-Host 'AKIRA · 16.3.5'
# El runtime vive fuera de %LOCALAPPDATA%\Akira. Python instalado desde Microsoft Store
# puede virtualizar/redirigir esa carpeta hacia LocalCache\Local; si el venv vive allí,
# PowerShell puede buscarlo en una ruta distinta a la que Python terminó usando.
$runtimeRoot = Join-Path $env:USERPROFILE '.akira_runtime'
$venv = Join-Path $runtimeRoot 'venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
$venvPythonw = Join-Path $venv 'Scripts\pythonw.exe'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

function Test-AkiraPython {
    param([string]$Exe, [string[]]$PrefixArgs = @())
    if (-not $Exe) { return $false }
    try {
        & $Exe @PrefixArgs -c "import sys,struct; raise SystemExit(0 if (sys.version_info >= (3,10) and struct.calcsize('P')*8 == 64) else 3)" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function New-AkiraVenv {
    param([string]$Exe, [string[]]$PrefixArgs = @())
    try {
        if (Test-Path $venv) { Remove-Item -LiteralPath $venv -Recurse -Force -ErrorAction Stop }
        & $Exe @PrefixArgs -m venv --copies $venv
        if ($LASTEXITCODE -ne 0) { return $false }
        return (Test-AkiraPython -Exe $venvPython)
    } catch { return $false }
}

if (-not (Test-AkiraPython -Exe $venvPython)) {
    $candidates = @()
    $programsPython = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    if (Test-Path $programsPython) {
        Get-ChildItem -LiteralPath $programsPython -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | ForEach-Object {
            $exe = Join-Path $_.FullName 'python.exe'
            if (Test-Path $exe) { $candidates += [pscustomobject]@{ Exe=$exe; Args=@() } }
        }
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $launcher) { $launcher = Get-Command py -ErrorAction SilentlyContinue }
    if ($launcher) { $candidates += [pscustomobject]@{ Exe=$launcher.Source; Args=@('-3') } }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($python) { $candidates += [pscustomobject]@{ Exe=$python.Source; Args=@() } }

    $made = $false
    foreach ($candidate in $candidates) {
        if ((Test-AkiraPython -Exe $candidate.Exe -PrefixArgs $candidate.Args) -and (New-AkiraVenv -Exe $candidate.Exe -PrefixArgs $candidate.Args)) {
            $made = $true
            break
        }
    }

    if (-not $made -and (Get-Command winget -ErrorAction SilentlyContinue)) {
        & winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
        $python311 = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'
        if ((Test-AkiraPython -Exe $python311) -and (New-AkiraVenv -Exe $python311)) { $made = $true }
    }
}

if (-not (Test-AkiraPython -Exe $venvPython)) { throw 'No se pudo preparar Python 3.10+ de 64 bits. Akira intento Python normal, py launcher y Microsoft Store sin usar una ruta virtualizada.' }
if (-not (Test-Path $venvPythonw)) { $venvPythonw = $venvPython }
Write-Host 'Akira: instalando dependencias...'
& $venvPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de dependencias.' }

$releaseHelper=Join-Path $PSScriptRoot 'install_release.py'
function Invoke-AkiraRelease {
    param([string[]]$Arguments)
    $lines=@(& $venvPython $releaseHelper @Arguments)
    $helperExit=$LASTEXITCODE
    $body=$lines -join [Environment]::NewLine
    try { $result=$body | ConvertFrom-Json } catch { throw ('Respuesta inválida del instalador: '+$body) }
    if ($null -eq $helperExit -or $helperExit -ne 0 -or $result.status -eq 'FAILED') {
        $reason=$result.error
        if (-not $reason) { $reason=$body }
        throw ('Instalación '+$Arguments[0]+': '+$reason)
    }
    return $result
}
$installPhase='Localizar la instalación y sus datos vigentes'
$current=Invoke-AkiraRelease -Arguments @('current','--runtime-root',$runtimeRoot,'--legacy-root',$legacyApp)
$installPhase='Inspeccionar versiones antiguas antes de instalar'
$detectedOldReleases=Invoke-AkiraRelease -Arguments @('inspect','--runtime-root',$runtimeRoot)
$maintenancePreview=Invoke-AkiraRelease -Arguments @('inspect-maintenance','--runtime-root',$runtimeRoot,'--diagnostic',$diagnostic)
Write-Host ('Diagnósticos históricos identificados: '+@($maintenancePreview.removable).Count+' candidatos para limpieza después de verificar la actualización.')
Write-Host ('Revisión previa: '+@($detectedOldReleases.old_releases).Count+' versiones antiguas verificadas. Se retirarán solo tras migrar datos y activar correctamente.')
$oldRoot=$current.root
$sourceConfig='__NONE__'
if ($oldRoot) { $sourceConfig=Join-Path $oldRoot 'akira_config.json' }
$migratedConfig=Join-Path $PSScriptRoot 'akira_config_migrated.json'
$restoreInfo=Join-Path $PSScriptRoot 'akira_restore_info.json'
$installPhase='Recuperar configuración y preferencias de la IA'
& $venvPython (Join-Path $PSScriptRoot 'migrate_v11_settings.py') $sourceConfig $migratedConfig --search-root $env:LOCALAPPDATA --restore-file $restoreInfo
if ($LASTEXITCODE -ne 0) { throw 'Falló la migración. La instalación anterior se conserva.' }
# One-click native setup verified the official model and the llama.cpp binary.
# Configure the *new* release only; never mutate the existing active config.
if ($env:AKIRA_AI_SERVER -and $env:AKIRA_AI_MODEL) {
    if (-not (Test-Path -LiteralPath $env:AKIRA_AI_SERVER -PathType Leaf) -or -not (Test-Path -LiteralPath $env:AKIRA_AI_MODEL -PathType Leaf)) {
        throw 'La IA local descargada no está completa; no se sustituye la versión anterior.'
    }
    $configObj = Get-Content -LiteralPath $migratedConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $configObj.assistant) { throw 'No existe configuración de asistente para integrar llama.cpp.' }
    $configObj.assistant.local_runtime_enabled = $true
    $configObj.assistant.local_runtime_exe = [string]$env:AKIRA_AI_SERVER
    $configObj.assistant.local_runtime_model = [string]$env:AKIRA_AI_MODEL
    $configObj.assistant.local_runtime_idle_seconds = 30
    $configObj.assistant.local_endpoint = 'http://127.0.0.1:18942/v1/chat/completions'
    $configObj.assistant.local_model = 'qwen3-4b-instruct-2507-Q4_K_M.gguf'
    $configObj.assistant.local_model_lite = 'qwen3-4b-instruct-2507-Q4_K_M.gguf'
    $configObj.assistant.auto_install_local_ai = $false
    $configObj | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $migratedConfig -Encoding UTF8
    Write-Host 'IA local: modelo y servidor verificados; configuración preparada en la nueva versión.'
}

$installPhase='Validar el paquete y la configuración'
$installPhase='Comprobar escritura y reemplazo del estado del asistente en Windows'
$progressTestLog=Join-Path $diagnostic 'PRUEBA_ESTADO_ASISTENTE.txt'
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'PREPARAR_OLLAMA.ps1') -SelfTestProgress *> $progressTestLog
if ($LASTEXITCODE -ne 0) {throw ('La prueba real de escritura del asistente falló. Revisa '+$progressTestLog+'. La instalación anterior se conserva.')}
$installPhase='Validar el paquete y la configuración'
Write-Host 'Validando ejecución, fuentes y carreras MT5 con simulador SIN CUENTA REAL...'
& $venvPython (Join-Path $PSScriptRoot 'install_checks.py') --config $migratedConfig --log-dir $diagnostic
$testExit=$LASTEXITCODE
if ($null -eq $testExit -or $testExit -ne 0) {
    $reason='El proceso de validación devolvió código '+$testExit
    $failedReportPath=Join-Path $diagnostic 'INSTALL_RESULT_AKIRA.json'
    if (Test-Path -LiteralPath $failedReportPath) {
        try {
            $failedReport=Get-Content -LiteralPath $failedReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($failedReport.message) { $reason=$failedReport.message }
        } catch { Write-Host 'No se pudo leer el resumen; los registros completos se conservan.' }
    }
    throw ('Validación detenida. '+$reason+' La instalación anterior se conserva.')
}
$reportPath=Join-Path $diagnostic 'INSTALL_RESULT_AKIRA.json'
if (-not (Test-Path -LiteralPath $reportPath)) { throw 'Falta el resultado verificable de las pruebas.' }
$report=Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($report.status -ne 'PASSED' -or $report.exit_code -ne 0 -or $report.build -ne $expectedBuild) {
    throw ('La versión de las pruebas no coincide con el paquete. Se esperaba '+$expectedBuild+' y se recibió '+[string]$report.build+'. Se conserva la instalación anterior.')
}
Write-Host ('Validación correcta: '+$report.tests_run+' pruebas. Preparando carpeta nueva...')
$installPhase='Confirmar que no se abrió otra instancia de Akira'
Stop-AkiraInstances -Reason 'preparar la nueva versión'
$installPhase='Preparar versión nueva y recuperar datos'
$prepareArgs=@('prepare','--runtime-root',$runtimeRoot,'--source',$PSScriptRoot,'--config',$migratedConfig,'--diagnostic',$diagnostic,'--restore-info',$restoreInfo)
if ($oldRoot) { $prepareArgs+=@('--current',$oldRoot) }
# Conserva @('state','logs','exports','AKIRA_SECRETS.json') y recupera memorias anteriores.
# Si un reemplazo anterior dejó Akira en Akira.backup.pre11.*, el helper recupera esa copia.
$prepared=Invoke-AkiraRelease -Arguments $prepareArgs
$app=$prepared.root
$installPhase='Construir y verificar aplicación AKIRA.exe'
& $venvPython (Join-Path $app 'build_windows.py') --source $app --diagnostic $diagnostic
if ($LASTEXITCODE -ne 0) { throw 'Falló la construcción de AKIRA.exe. La versión anterior sigue intacta.' }
$akiraExe=Join-Path $app 'native\AKIRA\AKIRA.exe'
if (-not (Test-Path -LiteralPath $akiraExe)) { throw 'No se generó AKIRA.exe; no se activa el acceso directo.' }
Write-Host ('Versión nueva preparada: '+$app)
$installPhase='Preparar el acceso directo nuevo'
$desktop=[Environment]::GetFolderPath('Desktop')
$shortcut=Join-Path $desktop 'Akira.lnk'
$newShortcut=Join-Path $diagnostic 'Nueva_Akira.lnk'
& $venvPython (Join-Path $app 'windows_identity.py') --shortcut $newShortcut --executable $akiraExe --root $app
if ($LASTEXITCODE -ne 0) { throw 'No se preparó el acceso directo con la identidad y el logo de AKIRA; no se activa.' }
$installPhase='Confirmar que Akira sigue cerrada antes de activar'
Stop-AkiraInstances -Reason 'activar la nueva versión'
$installPhase='Activar el acceso directo y la versión nueva'
$activation=Invoke-AkiraRelease -Arguments @('activate','--runtime-root',$runtimeRoot,'--release',$app,'--diagnostic',$diagnostic,'--shortcut',$shortcut,'--new-shortcut',$newShortcut)
$activated=$true
# Repair only AKIRA pins that still point at the previous installation.
try {
    if ($oldRoot) { & $venvPython (Join-Path $app 'windows_identity.py') --repair-pins $shortcut --previous-root $oldRoot --diagnostic $diagnostic }
    if ($oldRoot -and $LASTEXITCODE -ne 0) { Write-Warning 'Se conservó un anclaje antiguo; el acceso directo nuevo de AKIRA está listo.' }
} catch { Write-Warning 'El acceso directo nuevo está listo; Windows no permitió actualizar un anclaje antiguo.' }
# Never auto-start the program during installation. A running AKIRA.exe locks the
# new release and can make later cleanup fail while reporting contradictory state.
# Launch from the desktop shortcut ONLY after the installer has reported success.
$installPhase='Registrar la aplicación y finalizar la activación'
# Visible in Windows Settings > Apps > Installed apps with a real native EXE.
try {
    $nativeUninstaller=Join-Path $app 'AKIRA_Desinstalador.exe'
    if (-not (Test-Path -LiteralPath $nativeUninstaller -PathType Leaf)) { throw 'Falta AKIRA_Desinstalador.exe' }
    $uninstallKey='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AKIRA'
    New-Item -Path $uninstallKey -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayName -Value 'AKIRA' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayVersion -Value '16.3.5' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name Publisher -Value 'AKIRA' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name InstallLocation -Value $app -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayIcon -Value $akiraExe -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name UninstallString -Value ('"'+$nativeUninstaller+'"') -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null
} catch { Write-Warning ('Akira funciona, pero Windows no registró su desinstalador: '+$_.Exception.Message) }
# Record success only after optional post-install cleanup has been attempted.
# Do not retire the previous code until the new app is active. A failed
# migration or validation must always leave the old installation intact.
try {
    $retired=Invoke-AkiraRelease -Arguments @('cleanup','--runtime-root',$runtimeRoot)
    Write-Host ('Limpieza segura: '+@($retired.removed).Count+' versiones retiradas; '+@($retired.deferred).Count+' carpetas pospuestas por archivos en uso.')
} catch {
    Write-Warning ('Akira quedó instalada, pero algunos archivos antiguos se conservaron por seguridad: '+$_.Exception.Message)
}
# Verify the active pointer still matches the tested executable before success.
$installPhase='Confirmar activación completa'
$activeInfo=Get-Content -LiteralPath (Join-Path $runtimeRoot 'active_install.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ([IO.Path]::GetFullPath([string]$activeInfo.root) -ne [IO.Path]::GetFullPath([string]$app)) {
    throw 'El puntero de versión activa no coincide con la aplicación verificada.'
}
if (-not (Test-Path -LiteralPath $akiraExe -PathType Leaf) -or -not (Test-Path -LiteralPath $shortcut -PathType Leaf)) {
    throw 'La versión nueva no tiene ejecutable o acceso directo verificable.'
}
$hostResult=[ordered]@{status='INSTALLED';build=$expectedBuild;phase='COMPLETED';root=$app;previous_root=$oldRoot;autostart=$false;diagnostic=$diagnostic}
$hostResult | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $diagnostic 'INSTALL_HOST_RESULT.json') -Encoding UTF8
$activated=$false;$installCommitted=$true
# Never remove evidence during preparation/activation. Only retire old
# generated installer logs after the active native app and launcher are verified.
try {
    $maint=Invoke-AkiraRelease -Arguments @('cleanup-maintenance','--runtime-root',$runtimeRoot,'--diagnostic',$diagnostic)
    Write-Host ('Mantenimiento: '+@($maint.removed).Count+' diagnósticos antiguos retirados; '+@($maint.deferred).Count+' pendientes.')
} catch { Write-Warning ('Limpieza de diagnósticos pospuesta, sin afectar la instalación activa: '+$_.Exception.Message) }
Write-Host 'AKIRA 16.3.5 instalada y verificada. Ya puedes iniciarla desde su acceso directo.'
if ($oldRoot) { Write-Host ('Instalación anterior: '+$oldRoot) }
Write-Host ('Registro de instalación: '+$diagnostic)
} catch {
    # Capture the original Windows error before attempting recovery or writing logs.
    $originalError=$_
    $rollbackDetail='La carpeta anterior no se movió ni se borró.'
    $needsRollback=$activated
    $transactionPath=Join-Path $diagnostic 'INSTALL_ACTIVATION.json'
    if (-not $installCommitted -and -not $needsRollback -and (Test-Path -LiteralPath $transactionPath)) {
        try {
            $transaction=Get-Content -LiteralPath $transactionPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $needsRollback=$transaction.status -in @('ACTIVATING','ACTIVATED')
        } catch { $rollbackDetail+=' No se pudo leer la transacción de activación: '+$_.Exception.Message }
    }
    if ($needsRollback) {
        try {
            Invoke-AkiraRelease -Arguments @('rollback','--runtime-root',$runtimeRoot,'--diagnostic',$diagnostic) | Out-Null
            $rollbackDetail+=' Acceso directo y versión activa anteriores restaurados.'
        } catch { $rollbackDetail+=' Error de recuperación: '+$_.Exception.ToString() }
    }
    $hostResult=[ordered]@{status='FAILED';build=$expectedBuild;phase=$installPhase;root=$app;previous_root=$oldRoot;error=$originalError.Exception.ToString();error_id=$originalError.FullyQualifiedErrorId;position=$originalError.InvocationInfo.PositionMessage;stack=$originalError.ScriptStackTrace;recovery=$rollbackDetail;diagnostic=$diagnostic}
    $errorFile=Join-Path $diagnostic 'ERROR_AKIRA.txt'
    try {
        $hostResult | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $diagnostic 'INSTALL_HOST_RESULT.json') -Encoding UTF8
        $parts=New-Object 'System.Collections.Generic.List[string]'
        $parts.Add('AKIRA - ERROR ORIGINAL DE INSTALACIÓN')
        $parts.Add(($hostResult | ConvertTo-Json -Depth 8))
        foreach ($name in @('INSTALL_CURRENT_ERROR.json','INSTALL_PREPARE_ERROR.json','INSTALL_ACTIVATE_ERROR.json','INSTALL_ROLLBACK_ERROR.json','INSTALL_RESULT_AKIRA.json','INSTALL_TESTS_ERR.log','PRUEBA_DESINSTALADOR.json','NATIVE_SELF_CHECK.json','NATIVE_SELF_CHECK_STDERR.log','NATIVE_SELF_CHECK_TIMEOUT.txt','NATIVE_APPLICATION.json','NATIVE_BUILD.log')) {
            $path=Join-Path $diagnostic $name
            if (Test-Path -LiteralPath $path) { $parts.Add([Environment]::NewLine+'ARCHIVO: '+$name+[Environment]::NewLine); $parts.Add([string](Get-Content -LiteralPath $path -Raw -Encoding UTF8)) }
        }
        [IO.File]::WriteAllText($errorFile,($parts -join [Environment]::NewLine),(New-Object System.Text.UTF8Encoding($true)))
    } catch { Write-Host ('No se pudo escribir el informe adicional: '+$_.Exception.Message) }
    Write-Host ('ERROR en '+$installPhase+': '+$originalError.Exception.Message) -ForegroundColor Red
    Write-Host $rollbackDetail
    Write-Host ('Diagnóstico conservado en: '+$diagnostic)
    if (Test-Path -LiteralPath $errorFile) {
        Write-Host ('Archivo completo para adjuntar: '+$errorFile)
        # GUI exposes the diagnostic folder; do not open an unrelated Notepad window.
    }
    exit 1
} finally {
    if ($mutexOwned -and $installerMutex) { try { $installerMutex.ReleaseMutex() } catch {} }
    if ($installerMutex) { $installerMutex.Dispose() }
    if ($transcriptStarted) { try { Stop-Transcript | Out-Null } catch {} }
}
# Explicitly signal success to the GUI. $LASTEXITCODE from an optional
# auxiliary process must not turn a committed installation into a false error.
exit 0
