param([switch]$SelfTestProgress)
$ErrorActionPreference = 'Stop'
$OutputEncoding = New-Object Text.UTF8Encoding($false)
try { [Console]::OutputEncoding = $OutputEncoding } catch { }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$progressTestRoot=$null
if ($SelfTestProgress) {
    $progressTestRoot=Join-Path ([IO.Path]::GetTempPath()) ('AKIRA_PROGRESS_'+[Guid]::NewGuid().ToString('N'))
    $state=Join-Path $progressTestRoot 'state';$shared=Join-Path $progressTestRoot 'shared'
} else {
    $state=Join-Path $root 'state';$shared=Join-Path $env:LOCALAPPDATA 'AKIRA'
}
New-Item -ItemType Directory -Force -Path $state,$shared | Out-Null
$profilePath = Join-Path $state 'akira_local_ai_profile.json'
$sharedProfile = Join-Path $shared 'assistant_startup.json'
$logPath = Join-Path $root 'logs\ASISTENTE_INICIO.log'
$script:profile = @{ready=$false;vision_ready=$false;pid=$PID;phase='STARTING';detail='Iniciando el asistente de AKIRA.';credits_required=$false;recovery_active=$true;inference_checked=$false;inference_ok=$false}
$script:lastWrite = 0.0
$script:ownsMutex = $false
$mutex = $null
$base = 'http://127.0.0.1:11434'

function Save-Progress([string]$phase,[string]$detail,[bool]$sharedWrite=$true) {
    $script:profile.phase = $phase
    $script:profile.detail = $detail
    $script:profile.updated = (Get-Date).ToUniversalTime().ToString('o')
    $script:profile.heartbeat = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
    $json = $script:profile | ConvertTo-Json -Depth 5
    $paths = @($profilePath)
    if ($sharedWrite) { $paths += $sharedProfile }
    foreach ($path in $paths) {
        $tmp = $path + '.' + $PID + '.tmp'
        [IO.File]::WriteAllText($tmp,$json,(New-Object Text.UTF8Encoding($false)))
        for ($attempt=0;$attempt -lt 4;$attempt++) {
            try {
                if ([IO.File]::Exists($path)) { [IO.File]::Replace($tmp,$path,[System.Management.Automation.Language.NullString]::Value) }
                else { [IO.File]::Move($tmp,$path) }
                break
            } catch {
                if ($attempt -ge 3) { throw }
                Start-Sleep -Milliseconds 60
            }
        }
    }
    $script:lastWrite = $script:profile.heartbeat
}

if ($SelfTestProgress) {
    try {
        Save-Progress 'STARTING' 'Creación del estado de prueba.'
        Save-Progress 'VERIFYING' 'Reemplazo del estado existente: verificación.'
        Save-Progress 'READY' 'Prueba completada: reparación.'
        foreach ($path in @($profilePath,$sharedProfile)) {
            $check=Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json
            if ($check.phase -ne 'READY' -or $check.detail -ne 'Prueba completada: reparación.') {throw 'El archivo reemplazado no conserva estado y UTF-8.'}
        }
        Write-Output '{"status":"PASSED","existing_file_replacements":4,"network_used":false}'
        exit 0
    } catch {Write-Error ('Falló la escritura y reemplazo del estado: '+$_.Exception.Message);exit 1}
    finally {if ($progressTestRoot -and (Test-Path -LiteralPath $progressTestRoot)) {Remove-Item -LiteralPath $progressTestRoot -Recurse -Force}}
}
New-Item -ItemType Directory -Force -Path (Join-Path $root 'logs') | Out-Null

function Get-SetupError($failure) {
    $message = $failure.Exception.Message
    try {
        if ($failure.Exception.Response) {
            $reader = [IO.StreamReader]::new($failure.Exception.Response.GetResponseStream())
            try { $detail=$reader.ReadToEnd();if ($detail) { $message += ' '+$detail.Substring(0,[math]::Min(4096,$detail.Length)) } }
            finally { $reader.Dispose() }
        }
    } catch { }
    return $message
}

function Test-AssistantResponse([string]$model) {
    $script:profile.inference_checked=$false;$script:profile.inference_ok=$false
    $script:profile.text_model=$model
    Save-Progress 'VERIFYING' 'Probando una respuesta real del asistente. El primer inicio puede tardar.'
    $request=[Net.HttpWebRequest]::Create($base+'/api/generate')
    $request.Method='POST';$request.ContentType='application/json';$request.Timeout=90000;$request.ReadWriteTimeout=90000
    $payload=@{model=$model;prompt='Responde solamente: AKIRA listo';stream=$false;keep_alive='5m';options=@{num_predict=8;num_ctx=1024;temperature=0}}
    if ($model -match '^(qwen3|deepseek)') { $payload.think=$false }
    $bytes=[Text.Encoding]::UTF8.GetBytes(($payload|ConvertTo-Json -Depth 5 -Compress));$request.ContentLength=$bytes.Length
    $stream=$request.GetRequestStream();try {$stream.Write($bytes,0,$bytes.Length)} finally {$stream.Dispose()}
    $pending=$request.BeginGetResponse($null,$null);$deadline=(Get-Date).AddSeconds(90)
    try {
        while (-not $pending.AsyncWaitHandle.WaitOne(1000)) {
            if ((Get-Date) -ge $deadline) { $request.Abort();throw 'El asistente no completo una respuesta en 90 segundos.' }
            Save-Progress 'VERIFYING' 'Cargando y comprobando una respuesta real; la preparacion sigue activa.'
        }
        $response=$request.EndGetResponse($pending)
        $reader=[IO.StreamReader]::new($response.GetResponseStream())
        try {$result=$reader.ReadToEnd()|ConvertFrom-Json} finally {$reader.Dispose();$response.Dispose()}
        if ($result.error) { throw [string]$result.error }
        if (-not $result.done -or -not ([string]$result.response).Trim()) { throw 'El asistente no devolvio una respuesta de texto completa.' }
        $script:profile.inference_checked=$true;$script:profile.inference_ok=$true
        $script:profile.Remove('error');$script:profile.verified_at=(Get-Date).ToUniversalTime().ToString('o')
    } catch {
        $script:profile.inference_checked=$true;$script:profile.inference_ok=$false
        throw
    } finally {$pending.AsyncWaitHandle.Close()}
}

function Find-Ollama {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $local = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path $local) { return $local }
    return $null
}

function Get-Models {
    $tags = Invoke-RestMethod -Uri ($base+'/api/tags') -TimeoutSec 3
    return ,@($tags.models | ForEach-Object { [string]$_.name })
}

function Receive-Model([string]$model,[string]$phase) {
    $script:profile.Remove('progress_pct');$script:profile.Remove('completed_bytes');$script:profile.Remove('total_bytes')
    Save-Progress $phase 'Conectando para descargar un componente del asistente.'
    $request = [Net.HttpWebRequest]::Create($base+'/api/pull')
    $request.Method = 'POST';$request.ContentType = 'application/json'
    $request.Timeout = 60000;$request.ReadWriteTimeout = 60000
    $body = [Text.Encoding]::UTF8.GetBytes((@{model=$model;stream=$true}|ConvertTo-Json -Compress))
    $request.ContentLength = $body.Length
    $stream = $request.GetRequestStream()
    try { $stream.Write($body,0,$body.Length) } finally { $stream.Dispose() }
    $response = $request.GetResponse()
    $reader = [IO.StreamReader]::new($response.GetResponseStream())
    $success = $false
    try {
        while ($null -ne ($line=$reader.ReadLine())) {
            if (-not $line.Trim()) { continue }
            $row = $line | ConvertFrom-Json
            if ($row.error) { throw [string]$row.error }
            $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
            $download = ($null -ne $row.total -and [double]$row.total -gt 0 -and $null -ne $row.completed)
            if ($download) {
                $script:profile.completed_bytes = [double]$row.completed
                $script:profile.total_bytes = [double]$row.total
                $script:profile.progress_pct = [math]::Round(100.0*[double]$row.completed/[double]$row.total,1)
                $script:profile.layer = [string]$row.digest
            } else {
                $script:profile.Remove('progress_pct');$script:profile.Remove('completed_bytes');$script:profile.Remove('total_bytes')
            }
            if ($row.status -eq 'success') { $success=$true;break }
            if ($now-$script:lastWrite -ge 1) {
                if ($download) {
                    $label = if ($phase -eq 'VISION') { 'Vision: descargando capa' } else { 'Asistente: descargando capa' }
                    Save-Progress $phase ($label+' '+$script:profile.progress_pct+'% ('+[math]::Round([double]$row.completed/1MB,0)+' / '+[math]::Round([double]$row.total/1MB,0)+' MB).')
                } else {
                    $label = if ($phase -eq 'VISION') { 'Preparando vision; el chat ya esta disponible.' } else { 'Verificando los componentes descargados.' }
                    Save-Progress $(if ($phase -eq 'VISION') {'VISION'} else {'VERIFYING'}) $label
                }
            }
        }
    } finally { $reader.Dispose();$response.Dispose() }
    if (-not $success) { throw 'La descarga termino sin confirmacion de exito.' }
}

try {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $mutex = [Threading.Mutex]::new($false,('Local\AKIRA_Assistant_Setup_'+$sid))
    try { $script:ownsMutex=$mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $script:ownsMutex=$true }
    if (-not $script:ownsMutex) {
        Save-Progress 'WAITING' 'Otra preparacion de AKIRA esta en curso; se comparte su progreso.' $false
        exit 0
    }
    Save-Progress 'STARTING' 'Comprobando el servicio del asistente.'
    $exe = Find-Ollama
    if (-not $exe) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) { throw 'Windows no tiene disponible el instalador winget. Instala el servicio local y pulsa REPARAR ASISTENTE.' }
        Save-Progress 'INSTALLING' 'Instalando el servicio del asistente; esto solo se hace una vez.'
        $install = Start-Process -FilePath $winget.Source -ArgumentList 'install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements --disable-interactivity' -PassThru -WindowStyle Hidden
        $limit = (Get-Date).AddMinutes(30)
        while (-not $install.HasExited) {
            if ((Get-Date) -ge $limit) { throw 'La instalacion del servicio no termino en 30 minutos. Revisa el instalador de Windows.' }
            Save-Progress 'INSTALLING' 'Windows esta instalando el servicio del asistente.'
            Start-Sleep -Seconds 1;$install.Refresh()
        }
        $exe = Find-Ollama
        if (-not $exe) { throw ('No se instalo el servicio del asistente. Codigo de instalacion: '+$install.ExitCode) }
    }
    try { $models=Get-Models } catch {
        Save-Progress 'STARTING' 'Iniciando el servicio del asistente.'
        Start-Process -FilePath $exe -ArgumentList 'serve' -WindowStyle Hidden
        $models=$null
        for ($i=0;$i -lt 20;$i++) {
            try { $models=Get-Models;break } catch {
                Save-Progress 'STARTING' 'Esperando la respuesta del servicio del asistente.'
                Start-Sleep -Milliseconds 500
            }
        }
        if ($null -eq $models) { throw 'El servicio del asistente no respondio despues de iniciarlo. Revisa ASISTENTE_INICIO.log y el servicio local.' }
    }
    try { $ram=[double](Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB } catch { $ram=8.0 }
    $textModel = if ($ram -ge 40.0) {'qwen3:30b-a3b'} elseif ($ram -ge 22.0) {'qwen3:14b'} elseif ($ram -ge 13.0) {'qwen3:8b'} else {'qwen3:4b'}
    $configuredModel='auto';$configuredLite='qwen3:4b'
    try {
        $config=Get-Content -Raw -Encoding UTF8 (Join-Path $root 'akira_config.json')|ConvertFrom-Json
        if ($config.assistant.local_model) {$configuredModel=[string]$config.assistant.local_model}
        if ($config.assistant.local_model_lite) {$configuredLite=[string]$config.assistant.local_model_lite}
    } catch { }
    # Honor the installed configured model before considering an automatic RAM tier.
    if ($configuredModel -ne 'auto') {
        $textModel=$configuredModel
        foreach ($candidate in @($configuredModel,$configuredLite,'qwen3:8b','qwen3:4b','gemma3:4b')) {
            $installed=@($models|Where-Object { $_ -eq $candidate -or $_.StartsWith($candidate+'-') -or $_.StartsWith($candidate+':') })
            if ($installed.Count -gt 0) { $textModel=$installed[0];break }
        }
    } else {
        foreach ($candidate in @('qwen3:30b-a3b','qwen3:14b','qwen3:8b','qwen3:4b','gemma3:4b')) {
            $installed=@($models|Where-Object { $_ -eq $candidate -or $_.StartsWith($candidate+'-') -or $_.StartsWith($candidate+':') })
            if ($installed.Count -gt 0) { $textModel=$installed[0];break }
        }
    }
    $visionModel='gemma3:4b'
    $script:profile.text_model=$textModel;$script:profile.vision_model=$visionModel
    $script:profile.ram_gb=[math]::Round($ram,1);$script:profile.endpoint=$base+'/api/chat'
    if ($models -notcontains $textModel) { Receive-Model $textModel 'DOWNLOADING' }
    Save-Progress 'VERIFYING' 'Comprobando que el asistente descargado esta disponible.'
    $models=Get-Models
    if ($models -notcontains $textModel) { throw 'El servicio no confirma el modelo de texto despues de la descarga.' }
    try { Test-AssistantResponse $textModel } catch {
        $primaryError=Get-SetupError $_
        Add-Content -Encoding UTF8 $logPath ((Get-Date).ToUniversalTime().ToString('o')+' RESPUESTA '+$primaryError)
        $fallback=if ($configuredLite -ne $textModel) {$configuredLite} else {'qwen3:4b'}
        if ($fallback -eq $textModel) {throw ('El asistente instalado no pudo responder: '+$primaryError)}
        $script:profile.primary_error=$primaryError;$script:profile.text_model=$fallback
        Save-Progress 'VERIFYING' 'Probando el asistente ligero para recuperar la conversacion.'
        if ($models -notcontains $fallback) {Receive-Model $fallback 'DOWNLOADING'}
        Test-AssistantResponse $fallback
        $textModel=$fallback
    }
    $script:profile.ready=$true;$script:profile.recovery_active=$false
    Save-Progress 'READY'  'El chat de AKIRA esta disponible.'
    # Vision cannot hold the conversational assistant in a loading state.
    try {
        if ($models -notcontains $visionModel) { Receive-Model $visionModel 'VISION' }
        $models=Get-Models;$script:profile.vision_ready=($models -contains $visionModel)
        Save-Progress 'READY' 'El asistente de AKIRA esta disponible.'
    } catch {
        $script:profile.vision_error=$_.Exception.Message
        Add-Content -Encoding UTF8 $logPath ((Get-Date).ToUniversalTime().ToString('o')+' VISION '+$_.Exception.Message)
        Save-Progress 'READY' 'Chat disponible. La vision no termino de descargarse; puedes reintentar la reparacion.'
    }
    Write-Host 'AKIRA: asistente preparado. El estado del chat se confirma en la aplicacion.'
} catch {
    $script:profile.ready=$false;$script:profile.error=Get-SetupError $_
    Add-Content -Encoding UTF8 $logPath ((Get-Date).ToUniversalTime().ToString('o')+' ERROR '+$script:profile.error)
    try { Save-Progress 'FAILED' ($script:profile.error+' Pulsa REPARAR ASISTENTE; el error quedo en ASISTENTE_INICIO.log.') } catch { }
    Write-Host ('AKIRA: no se pudo preparar el asistente. '+$script:profile.error)
    exit 1
} finally {
    if ($script:ownsMutex -and $mutex) { $mutex.ReleaseMutex() }
    if ($mutex) { $mutex.Dispose() }
}
