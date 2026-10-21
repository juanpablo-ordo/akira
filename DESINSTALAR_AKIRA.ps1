param([switch]$SelfTest,[switch]$Worker,[switch]$EraseAll,[string]$ResultPath)
$ErrorActionPreference='Stop'

function Write-AkiraJson {
    param([string]$Path,$Value)
    $parent=Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary=$Path+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
    try {
        [IO.File]::WriteAllText($temporary,($Value | ConvertTo-Json -Depth 12),(New-Object System.Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
}

function New-AkiraRemovalContext {
    param([string]$ProfileRoot,[string]$LocalRoot,[string]$DesktopRoot)
    [pscustomobject]@{profile=[IO.Path]::GetFullPath($ProfileRoot);local=[IO.Path]::GetFullPath($LocalRoot);
        desktop=[IO.Path]::GetFullPath($DesktopRoot);runtime=(Join-Path $ProfileRoot '.akira_runtime');
        backups=(Join-Path $ProfileRoot 'Akira_Datos_Conservados')}
}

function Assert-AkiraRealTree {
    param([string]$Path,[switch]$Tree)
    # Never copy/delete through junctions, symlinks or mount-point redirections.
    $cursor=[IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item=Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw ('Ruta redirigida; se conserva sin modificar: '+$cursor) }
        }
        $next=Split-Path -Parent $cursor
        if ($next -eq $cursor) { break };$cursor=$next
    }
    if (-not $Tree -or -not (Test-Path -LiteralPath $Path -PathType Container)) { return }
    $queue=New-Object 'System.Collections.Generic.Queue[string]';$queue.Enqueue($Path)
    while ($queue.Count -gt 0) {
        foreach ($item in @(Get-ChildItem -LiteralPath $queue.Dequeue() -Force)) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw ('Enlace dentro de la instalación; se conserva: '+$item.FullName) }
            if ($item.PSIsContainer) { $queue.Enqueue($item.FullName) }
        }
    }
}

function Test-AkiraOwnedRoot {
    param([string]$Root)
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return $false }
    foreach ($name in @('Akira.py','akira_version.py','akira_config.json')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $name) -PathType Leaf)) { return $false }
    }
    return [bool]((Get-Content -LiteralPath (Join-Path $Root 'akira_version.py') -Raw -Encoding UTF8) -match 'BUILD_ID.*AKIRA_')
}

function Get-AkiraRemovalPlan {
    param($Context)
    $roots=New-Object 'System.Collections.Generic.List[string]'
    $releaseDir=Join-Path $Context.runtime 'releases'
    Assert-AkiraRealTree $Context.runtime
    if (Test-Path -LiteralPath $releaseDir -PathType Container) {
        foreach ($folder in @(Get-ChildItem -LiteralPath $releaseDir -Directory)) {
            if ($folder.Name -like 'Akira_*' -and (Test-AkiraOwnedRoot $folder.FullName)) {
                Assert-AkiraRealTree $folder.FullName -Tree;$roots.Add($folder.FullName)
            }
        }
    }
    foreach ($name in @('Akira','AKIRA_FINAL_V7','AKIRA_FINAL_V6','AKIRA_FINAL_V5','AKIRA_FINAL_V4','AKIRA_FINAL_V3','AKIRA_V207','AKIRA_V193','AKIRA_V191','AKIRA_V186')) {
        $legacy=Join-Path $Context.local $name
        if (Test-AkiraOwnedRoot $legacy) { Assert-AkiraRealTree $legacy -Tree;$roots.Add($legacy) }
    }
    $pointer=Join-Path $Context.runtime 'active_install.json';$active=$null
    if (Test-Path -LiteralPath $pointer) {
        $record=Get-Content -LiteralPath $pointer -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $record.root) { throw 'La instalación activa no identifica su carpeta; no se borra nada.' }
        $active=[IO.Path]::GetFullPath([string]$record.root)
        if ($roots -notcontains $active) { throw 'La instalación registrada no está dentro de las carpetas verificadas de AKIRA. No se borra nada.' }
    } elseif ($roots.Count -gt 0) {
        $active=($roots | Sort-Object { (Get-Item -LiteralPath (Join-Path $_ 'akira_config.json')).LastWriteTimeUtc } -Descending | Select-Object -First 1)
    }
    [pscustomobject]@{context=$Context;roots=@($roots.ToArray());active=$active;pointer=$pointer;
        count=$roots.Count;data_names=@('akira_config.json','AKIRA_SECRETS.json','state','logs','exports','studio')}
}

function Test-AkiraOwnedProcess {
    param($Process,[string[]]$Roots)
    foreach ($root in $Roots) {
        $exe=Join-Path $root 'native\AKIRA\AKIRA.exe'
        if ($Process.Name -ieq 'AKIRA.exe' -and $Process.ExecutablePath -ieq $exe) { return $true }
        if ($Process.Name -match '^python(w|[0-9]+([.][0-9]+)*)?[.]exe$') {
            $script=[regex]::Escape((Join-Path $root 'Akira.py'))
            if ([string]$Process.CommandLine -match ('(?i)(?:^|\s)"?'+$script+'"?(?=\s|$)')) { return $true }
        }
    }
    return $false
}

function Stop-AkiraOwnedProcesses {
    param($Plan)
    foreach ($row in @(Get-CimInstance Win32_Process)) {
        if (-not (Test-AkiraOwnedProcess $row $Plan.roots)) { continue }
        $process=Get-Process -Id $row.ProcessId -ErrorAction SilentlyContinue
        if ($process) {
            $closed=$process.CloseMainWindow()
            if ($closed) { $null=$process.WaitForExit(4000) }
        }
        # Re-query the path after waiting; never terminate a reused PID.
        $remaining=Get-CimInstance Win32_Process -Filter ('ProcessId='+$row.ProcessId)
        if ($remaining -and (Test-AkiraOwnedProcess $remaining $Plan.roots)) {
            Stop-Process -Id $row.ProcessId -ErrorAction Stop
        }
    }
    foreach ($row in @(Get-CimInstance Win32_Process)) {
        if (Test-AkiraOwnedProcess $row $Plan.roots) { throw 'AKIRA sigue abierta. Ciérrala antes de desinstalar; tus datos se conservan.' }
    }
}

function Copy-AkiraVerifiedData {
    param([string]$Source,[string]$Destination)
    if (-not (Test-Path -LiteralPath $Source)) { return }
    Assert-AkiraRealTree $Source
    $item=Get-Item -LiteralPath $Source -Force
    if ($item.PSIsContainer) {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
        foreach ($child in @(Get-ChildItem -LiteralPath $Source -Force)) {
            Copy-AkiraVerifiedData $child.FullName (Join-Path $Destination $child.Name)
        }
    } else {
        New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
        $before=(Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
        if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ne $before -or
            (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash -ne $before) {
            throw ('La copia no coincide o el archivo cambió: '+$Source+'. No se retira el programa.')
        }
    }
}

function Get-AkiraOwnedShortcuts {
    param($Plan)
    $paths=New-Object 'System.Collections.Generic.List[string]'
    $shell=New-Object -ComObject WScript.Shell
    $locations=@($Plan.context.desktop,(Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'))
    try {
        foreach ($location in $locations) {
            if (-not (Test-Path -LiteralPath $location -PathType Container)) { continue }
            foreach ($path in @(Get-ChildItem -LiteralPath $location -Filter '*.lnk' -File)) {
                $link=$shell.CreateShortcut($path.FullName)
                foreach ($root in $Plan.roots) {
                    $native=Join-Path $root 'native\AKIRA\AKIRA.exe';$script=Join-Path $root 'Akira.py'
                    if ($link.TargetPath -ieq $native -or
                        ($link.TargetPath -match '[\\/]pythonw?[.]exe$' -and $link.Arguments -match ([regex]::Escape($script)))) {
                        $paths.Add($path.FullName);break
                    }
                }
            }
        }
    } finally { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) }
    return @($paths.ToArray())
}

function Invoke-AkiraRemoval {
    param($Plan,[string[]]$Shortcuts=@(),[scriptblock]$MoveDirectory={param($From,$To) Move-Item -LiteralPath $From -Destination $To})
    if ($Plan.count -eq 0) { return [pscustomobject]@{status='NOT_INSTALLED';backup='';count=0} }
    # Revalidate before modifying anything (the review may have been open for hours).
    $fresh=Get-AkiraRemovalPlan $Plan.context
    if ($fresh.active -ne $Plan.active -or (($fresh.roots | Sort-Object) -join '|') -ne (($Plan.roots | Sort-Object) -join '|')) {
        throw 'La instalación cambió después de abrir el desinstalador. Vuelve a abrirlo; no se ha borrado nada.'
    }
    Assert-AkiraRealTree $Plan.context.backups
    $stamp=(Get-Date -Format 'yyyyMMdd_HHmmss')+'.'+[Guid]::NewGuid().ToString('N').Substring(0,8)
    $backup=Join-Path $Plan.context.backups $stamp
    New-Item -ItemType Directory -Path $backup | Out-Null
    $records=New-Object 'System.Collections.Generic.List[object]';$activeData=$null
    $index=0
    foreach ($root in $Plan.roots) {
        $index++;$dataRoot=Join-Path $backup ('versiones\'+$index.ToString('D3'))
        foreach ($name in $Plan.data_names) { Copy-AkiraVerifiedData (Join-Path $root $name) (Join-Path $dataRoot $name) }
        if ($root -eq $Plan.active) { $activeData=$dataRoot }
        $records.Add([pscustomobject]@{source=$root;data=$dataRoot})
    }
    if (-not $activeData -or -not (Test-Path -LiteralPath (Join-Path $activeData 'akira_config.json'))) { throw 'No se recuperó la configuración activa; el programa se conserva.' }
    Copy-AkiraVerifiedData $Plan.pointer (Join-Path $backup 'active_install.json')
    $preserved=Join-Path $Plan.context.runtime 'preserved_userdata.json'
    Copy-AkiraVerifiedData $preserved (Join-Path $backup 'previous_preserved_userdata.json')
    $links=New-Object 'System.Collections.Generic.List[object]';$index=0
    foreach ($path in $Shortcuts) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        $index++;$saved=Join-Path $backup ('accesos\'+$index+'.lnk')
        Copy-AkiraVerifiedData $path $saved;$links.Add([pscustomobject]@{path=$path;saved=$saved})
    }
    Write-AkiraJson (Join-Path $backup 'DESINSTALACION.json') @{status='BACKUP_VERIFIED';roots=@($records.ToArray());active_data=$activeData}
    $quarantine=Join-Path $Plan.context.runtime ('uninstall_staging\'+$stamp)
    New-Item -ItemType Directory -Path $quarantine -Force | Out-Null
    $moved=New-Object 'System.Collections.Generic.List[object]'
    try {
        foreach ($record in $records) {
            $target=Join-Path $quarantine ([string]$moved.Count)
            & $MoveDirectory $record.source $target
            $moved.Add([pscustomobject]@{original=$record.source;staged=$target})
        }
        Write-AkiraJson $preserved @{root=$activeData;backup=$backup;status='UNINSTALLED_DATA_PRESERVED';created=(Get-Date).ToUniversalTime().ToString('o')}
        foreach ($link in $links) { Remove-Item -LiteralPath $link.path -Force }
        if (Test-Path -LiteralPath $Plan.pointer) { Remove-Item -LiteralPath $Plan.pointer -Force }
    } catch {
        $original=$_;$rollbackErrors=New-Object 'System.Collections.Generic.List[string]'
        foreach ($record in (@($moved.ToArray()) | Sort-Object staged -Descending)) {
            try { Move-Item -LiteralPath $record.staged -Destination $record.original } catch { $rollbackErrors.Add($_.Exception.Message) }
        }
        foreach ($link in $links) { try { Copy-Item -LiteralPath $link.saved -Destination $link.path -Force } catch { $rollbackErrors.Add($_.Exception.Message) } }
        foreach ($pair in @(@((Join-Path $backup 'active_install.json'),$Plan.pointer),@((Join-Path $backup 'previous_preserved_userdata.json'),$preserved))) {
            try {
                if (Test-Path -LiteralPath $pair[0]) { Copy-Item -LiteralPath $pair[0] -Destination $pair[1] -Force }
                elseif (Test-Path -LiteralPath $pair[1]) { Remove-Item -LiteralPath $pair[1] -Force }
            } catch { $rollbackErrors.Add($_.Exception.Message) }
        }
        Write-AkiraJson (Join-Path $backup 'DESINSTALACION.json') @{status='FAILED';error=$original.Exception.Message;rollback_errors=@($rollbackErrors.ToArray());active_data=$activeData}
        throw ('No terminó la desinstalación: '+$original.Exception.Message+'. Datos conservados en '+$backup+'. Recuperación: '+(@($rollbackErrors.ToArray()) -join '; '))
    }
    $cleanupErrors=New-Object 'System.Collections.Generic.List[string]'
    try { Assert-AkiraRealTree $quarantine -Tree;Remove-Item -LiteralPath $quarantine -Recurse -Force } catch { $cleanupErrors.Add($_.Exception.Message) }
    # This virtual environment belongs to AKIRA and is reproducible. The
    # preserve-data mode must not leave its Python packages behind.
    foreach ($venvName in @('venv','.venv','ai')) {
        $runtimeVenv=Join-Path $Plan.context.runtime $venvName
        if (Test-Path -LiteralPath $runtimeVenv) {
            try { Assert-AkiraRealTree $runtimeVenv -Tree;Remove-Item -LiteralPath $runtimeVenv -Recurse -Force -ErrorAction Stop }
            catch { $cleanupErrors.Add($runtimeVenv+': '+$_.Exception.Message) }
        }
    }
    $status='UNINSTALLED';if ($cleanupErrors.Count -gt 0) { $status='PARTIAL_CLEANUP' }
    $result=[pscustomobject]@{status=$status;backup=$backup;count=$Plan.count;active_data=$activeData;cleanup_errors=@($cleanupErrors.ToArray())}
    Write-AkiraJson (Join-Path $backup 'DESINSTALACION.json') $result
    return $result
}

function Invoke-AkiraCompleteRemoval {
    param($Plan,[string[]]$Shortcuts=@())
    # Irreversible mode: no permanent backup. Scope to verified AKIRA-owned roots,
    # dedicated AKIRA data locations and shortcuts that point into those roots.
    $fresh=Get-AkiraRemovalPlan $Plan.context
    if ($fresh.active -ne $Plan.active -or (($fresh.roots | Sort-Object) -join '|') -ne (($Plan.roots | Sort-Object) -join '|')) {
        throw 'La instalación cambió durante la confirmación. No se ha eliminado nada.'
    }
    foreach ($root in $Plan.roots) { Assert-AkiraRealTree $root -Tree }
    $reserved=@($Plan.context.backups,(Join-Path $Plan.context.profile 'Akira_Diagnostico_Instalacion'))
    foreach ($dir in $reserved) { Assert-AkiraRealTree $dir -Tree }
    $quarantine=Join-Path $Plan.context.runtime ('uninstall_staging\erase_'+[Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $quarantine -Force | Out-Null
    $moved=New-Object 'System.Collections.Generic.List[object]'
    try {
        $i=0
        foreach ($root in $Plan.roots) {
            $i++
            $destination=Join-Path $quarantine ('release_'+$i)
            Move-Item -LiteralPath $root -Destination $destination -ErrorAction Stop
            $moved.Add([pscustomobject]@{source=$root;destination=$destination})
        }
    } catch {
        # No destructive work has begun; restore every staged release.
        $restore=@($moved.ToArray());[array]::Reverse($restore)
        foreach ($item in $restore) {
            if (-not $item -or -not (Test-Path -LiteralPath $item.destination)) { continue }
            Move-Item -LiteralPath $item.destination -Destination $item.source -ErrorAction Stop
        }
        throw ('No se pudieron separar todos los archivos. Se canceló antes de borrarlos: '+$_.Exception.Message)
    }
    $issues=New-Object 'System.Collections.Generic.List[string]'
    $removeOwned={ param([string]$Path)
        if (-not (Test-Path -LiteralPath $Path)) { return }
        try {
            Assert-AkiraRealTree $Path -Tree
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        } catch { $issues.Add($Path+': '+$_.Exception.Message) }
    }
    foreach ($item in $moved) { & $removeOwned $item.destination }
    foreach ($shortcut in $Shortcuts) {
        try { if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut -Force -ErrorAction Stop } }
        catch { $issues.Add($shortcut+': '+$_.Exception.Message) }
    }
    # Remove only explicitly owned AKIRA folders and metadata. Never delete MT5
    # accounts, unrelated programs, unknown AppData folders or Windows profiles.
    foreach ($path in @(
        $Plan.pointer,
        (Join-Path $Plan.context.runtime 'preserved_userdata.json'),
        (Join-Path $Plan.context.runtime '.venv'),
        (Join-Path $Plan.context.runtime 'venv'),
        (Join-Path $Plan.context.runtime 'ai'),
        (Join-Path $Plan.context.runtime 'releases'),
        $Plan.context.backups,
        (Join-Path $Plan.context.profile 'Akira_Diagnostico_Instalacion')
    )) { & $removeOwned $path }
    if ((Test-Path -LiteralPath $quarantine) -and
        @((Get-ChildItem -LiteralPath $quarantine -Force -ErrorAction SilentlyContinue)).Count -eq 0) {
        & $removeOwned $quarantine
    }
    foreach ($empty in @((Join-Path $Plan.context.runtime 'uninstall_staging'),$Plan.context.runtime)) {
        if (Test-Path -LiteralPath $empty -PathType Container) {
            try {
                Assert-AkiraRealTree $empty
                if (@(Get-ChildItem -LiteralPath $empty -Force).Count -eq 0) {
                    Remove-Item -LiteralPath $empty -Force -ErrorAction Stop
                }
            } catch { $issues.Add($empty+': '+$_.Exception.Message) }
        }
    }
    $status='UNINSTALLED_ALL'
    if ($issues.Count -gt 0) { $status='PARTIAL_CLEANUP' }
    # A full erase does not write new persistent backups, diagnostics or secrets.
    return [pscustomobject]@{status=$status;backup='';count=$Plan.count;cleanup_errors=@($issues.ToArray())}
}

function Test-AkiraRemoval {
    $sandbox=Join-Path ([IO.Path]::GetTempPath()) ('AKIRA_PRUEBA_DESINSTALAR_'+[Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $sandbox | Out-Null
    try {
        $context=New-AkiraRemovalContext $sandbox (Join-Path $sandbox 'Local') (Join-Path $sandbox 'Desktop')
        $first=Join-Path $context.runtime 'releases\Akira_TEST_1';$second=Join-Path $context.runtime 'releases\Akira_TEST_2'
        foreach ($root in @($first,$second)) {
            New-Item -ItemType Directory -Path (Join-Path $root 'state') -Force | Out-Null
            [IO.File]::WriteAllText((Join-Path $root 'Akira.py'),'# synthetic AKIRA')
            [IO.File]::WriteAllText((Join-Path $root 'akira_version.py'),'BUILD_ID="AKIRA_TEST"')
            [IO.File]::WriteAllText((Join-Path $root 'akira_config.json'),'{"account":123,"risk":2.17}')
            [IO.File]::WriteAllText((Join-Path $root 'state\chats.txt'),'memoria sintética á')
        }
        $other=Join-Path $context.runtime 'releases\OtroPrograma';New-Item -ItemType Directory -Path $other -Force | Out-Null
        [IO.File]::WriteAllText((Join-Path $other 'archivo.txt'),'conservar')
        Write-AkiraJson (Join-Path $context.runtime 'active_install.json') @{root=$second}
        $plan=Get-AkiraRemovalPlan $context
        if ($plan.count -ne 2 -or $plan.active -ne $second) { throw 'Plan sintético incorrecto' }
        $unrelated=[pscustomobject]@{Name='python.exe';ExecutablePath='C:\Otro\python.exe';CommandLine='python otro.py'}
        if (Test-AkiraOwnedProcess $unrelated $plan.roots) { throw 'Se identificaría un proceso ajeno' }
        $fake=[pscustomobject]@{Name='AKIRA.exe';ExecutablePath=(Join-Path $second 'native\AKIRA\AKIRA.exe');CommandLine=''}
        if (-not (Test-AkiraOwnedProcess $fake $plan.roots)) { throw 'No se reconoce la aplicación nativa' }
        $result=Invoke-AkiraRemoval $plan
        if ($result.status -ne 'UNINSTALLED' -or (Test-Path -LiteralPath $first) -or (Test-Path -LiteralPath $second)) { throw 'No se retiró el programa sintético' }
        if (-not (Test-Path -LiteralPath (Join-Path $other 'archivo.txt'))) { throw 'Se modificó un programa ajeno' }
        if ((Get-Content -LiteralPath (Join-Path $result.active_data 'state\chats.txt') -Raw -Encoding UTF8) -ne 'memoria sintética á') { throw 'No se conservó el chat' }
        $saved=Get-Content -LiteralPath (Join-Path $context.runtime 'preserved_userdata.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($saved.root -ne $result.active_data -or (Test-Path -LiteralPath $plan.pointer)) { throw 'Referencia de reinstalación incorrecta' }
        $empty=Invoke-AkiraRemoval (Get-AkiraRemovalPlan $context)
        if ($empty.status -ne 'NOT_INSTALLED') { throw 'Segunda desinstalación incorrecta' }
        Write-AkiraJson $plan.pointer @{root=(Join-Path $sandbox 'NO_AUTORIZADO')}
        $rejected=$false;try { Get-AkiraRemovalPlan $context | Out-Null } catch { $rejected=$true }
        if (-not $rejected) { throw 'Se aceptó una ruta fuera de la instalación' }
        # Deterministic failure on the second directory exercises real rollback.
        # Production uses Move-Item directly; this override exists only in the sandbox.
        $failureHome=Join-Path $sandbox 'FailureProfile'
        $failureContext=New-AkiraRemovalContext $failureHome (Join-Path $failureHome 'Local') (Join-Path $failureHome 'Desktop')
        $failureRoots=@((Join-Path $failureContext.runtime 'releases\Akira_A'),(Join-Path $failureContext.runtime 'releases\Akira_B'))
        foreach ($root in $failureRoots) {
            New-Item -ItemType Directory -Path $root -Force | Out-Null
            [IO.File]::WriteAllText((Join-Path $root 'Akira.py'),'# synthetic AKIRA')
            [IO.File]::WriteAllText((Join-Path $root 'akira_version.py'),'BUILD_ID="AKIRA_TEST"')
            [IO.File]::WriteAllText((Join-Path $root 'akira_config.json'),'{"account":123,"risk":2.17}')
        }
        $failurePointer=Join-Path $failureContext.runtime 'active_install.json'
        Write-AkiraJson $failurePointer @{root=$failureRoots[1]}
        $originalPointer=[IO.File]::ReadAllBytes($failurePointer)
        $failurePlan=Get-AkiraRemovalPlan $failureContext
        $rejected=$false
        try {
            Invoke-AkiraRemoval $failurePlan -MoveDirectory {
                param($From,$To)
                if ((Split-Path -Leaf $From) -eq 'Akira_B') { throw 'Fallo sintético de retirada' }
                Move-Item -LiteralPath $From -Destination $To
            } | Out-Null
        } catch { $rejected=$true }
        if (-not $rejected) { throw 'No se propagó el fallo de retirada' }
        foreach ($root in $failureRoots) { if (-not (Test-AkiraOwnedRoot $root)) { throw 'No se restauró una carpeta tras el fallo' } }
        if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($failurePointer)) -ne [Convert]::ToBase64String($originalPointer)) { throw 'La recuperación cambió la versión activa' }
        [pscustomobject]@{status='PASSED';data='SYNTHETIC';removed_releases=2;chat_preserved=$true;other_program_preserved=$true;external_root_rejected=$true;idempotent=$true;native_process_identified=$true;unrelated_process_preserved=$true;rollback_after_second_move_failure=$true}
    } finally { if (Test-Path -LiteralPath $sandbox) { Remove-Item -LiteralPath $sandbox -Recurse -Force } }
}

if ($SelfTest) {
    Test-AkiraRemoval | ConvertTo-Json -Depth 8
    exit 0
}

if ($Worker) {
    # Detached worker: copying, hashing and removal never block the WinForms event loop.
    # ResultPath is a diagnostic report, not a path to delete or modify.
    if (-not $ResultPath -or -not ([IO.Path]::GetFullPath($ResultPath)).StartsWith(
            ([IO.Path]::GetFullPath([IO.Path]::GetTempPath())),[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Ubicación inválida para el resultado de desinstalación.'
    }
    try {
        $ctx=New-AkiraRemovalContext $env:USERPROFILE $env:LOCALAPPDATA ([Environment]::GetFolderPath('Desktop'))
        $actual=Get-AkiraRemovalPlan $ctx
        if ($actual.count -eq 0 -and -not $EraseAll) {
            Write-AkiraJson $ResultPath @{status='NOT_INSTALLED';backup='';count=0}
            exit 0
        }
        Stop-AkiraOwnedProcesses $actual
        $links=@(Get-AkiraOwnedShortcuts $actual)
        if ($EraseAll) { $done=Invoke-AkiraCompleteRemoval $actual $links }
        else { $done=Invoke-AkiraRemoval $actual $links }
        Write-AkiraJson $ResultPath $done
        if ($done.status -eq 'PARTIAL_CLEANUP') { exit 2 }
        # Only unregister a confirmed successful uninstall.
        Remove-Item -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AKIRA' -Recurse -Force -ErrorAction SilentlyContinue
        exit 0
    } catch {
        Write-AkiraJson $ResultPath @{status='FAILED';error=$_.Exception.Message}
        exit 1
    }
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$context=New-AkiraRemovalContext $env:USERPROFILE $env:LOCALAPPDATA ([Environment]::GetFolderPath('Desktop'))
$form=New-Object System.Windows.Forms.Form
$form.Text='AKIRA · Desinstalar';$form.Size=New-Object System.Drawing.Size(710,560);$form.MinimumSize=$form.Size
$form.StartPosition='CenterScreen';$form.BackColor=[Drawing.Color]::FromArgb(9,17,29);$form.ForeColor=[Drawing.Color]::FromArgb(219,235,246)
$form.Font=New-Object System.Drawing.Font('Segoe UI',10)
# Ventana sin franja blanca. Controles de ventana propios y arrastre en el encabezado.
$form.FormBorderStyle='None';$form.ShowIcon=$true
try { $iconPath=Join-Path $PSScriptRoot 'assets\akira.ico';if (Test-Path -LiteralPath $iconPath) { $form.Icon=New-Object Drawing.Icon($iconPath) } } catch {}
$form.Font=New-Object Drawing.Font('Bahnschrift',10)
$top=New-Object Windows.Forms.Panel;$top.Location=New-Object Drawing.Point(0,0)
$top.Size=New-Object Drawing.Size($form.ClientSize.Width,40);$top.BackColor=[Drawing.Color]::FromArgb(13,36,52)
$form.Controls.Add($top)
$brand=New-Object Windows.Forms.Label;$brand.Text='◈  AKIRA  /  DESINSTALAR'
$brand.ForeColor=[Drawing.Color]::Turquoise;$brand.Font=New-Object Drawing.Font('Bahnschrift',11,[Drawing.FontStyle]::Bold)
$brand.Location=New-Object Drawing.Point(18,11);$brand.AutoSize=$true;$top.Controls.Add($brand)
$exit=New-Object Windows.Forms.Button;$exit.Text='×';$exit.FlatStyle='Flat'
$exit.FlatAppearance.BorderSize=0;$exit.ForeColor=[Drawing.Color]::White
$exit.BackColor=[Drawing.Color]::FromArgb(13,36,52)
$exit.Location=New-Object Drawing.Point(($form.ClientSize.Width-49),0);$exit.Size=New-Object Drawing.Size(49,40)
$exit.Add_Click({ if (-not $script:akiraWorkerProcess -or $script:akiraWorkerProcess.HasExited) { $form.Close() } });$top.Controls.Add($exit)
try {
 Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public static class AkiraMove { [DllImport("user32.dll")] public static extern bool ReleaseCapture(); [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hwnd,int msg,int wp,int lp); }' -ErrorAction SilentlyContinue
 $drag={param($s,$e) if ($e.Button -eq [Windows.Forms.MouseButtons]::Left) { [AkiraMove]::ReleaseCapture() | Out-Null;[AkiraMove]::SendMessage($form.Handle,0xA1,2,0) | Out-Null }}
 $top.Add_MouseDown($drag);$brand.Add_MouseDown($drag)
} catch {}

$title=New-Object System.Windows.Forms.Label
$title.Text='DESINSTALAR AKIRA';$title.AutoSize=$true;$title.Location=New-Object System.Drawing.Point(25,64)
$title.Font=New-Object System.Drawing.Font('Segoe UI',20,[Drawing.FontStyle]::Bold);$title.ForeColor=[Drawing.Color]::Turquoise;$form.Controls.Add($title)
$body=New-Object System.Windows.Forms.TextBox
$body.Multiline=$true;$body.ReadOnly=$true;$body.ScrollBars='Vertical';$body.BorderStyle='None'
$body.BackColor=$form.BackColor;$body.ForeColor=$form.ForeColor;$body.Location=New-Object System.Drawing.Point(28,119)
$body.Size=New-Object System.Drawing.Size(617,265);$body.Anchor='Top,Bottom,Left,Right';$form.Controls.Add($body)
$remove=New-Object System.Windows.Forms.Button
$remove.Text='CONSERVAR DATOS';$remove.Location=New-Object System.Drawing.Point(28,391);$remove.Size=New-Object System.Drawing.Size(292,46)
$remove.FlatStyle='Flat';$remove.ForeColor=[Drawing.Color]::White;$remove.BackColor=[Drawing.Color]::FromArgb(99,32,54);$remove.FlatAppearance.BorderColor=[Drawing.Color]::Salmon;$remove.Anchor='Bottom,Left';$form.Controls.Add($remove)
$erase=New-Object System.Windows.Forms.Button
$erase.Text='ELIMINAR TODO';$erase.Location=New-Object System.Drawing.Point(339,391)
$erase.Size=New-Object System.Drawing.Size(323,46);$erase.FlatStyle='Flat'
$erase.ForeColor=[Drawing.Color]::White;$erase.BackColor=[Drawing.Color]::FromArgb(123,32,55)
$erase.FlatAppearance.BorderColor=[Drawing.Color]::Salmon
$form.Controls.Add($erase)
$close=New-Object System.Windows.Forms.Button
$close.Text='CANCELAR';$close.Location=New-Object System.Drawing.Point(478,451);$close.Size=New-Object System.Drawing.Size(184,42)
$close.FlatStyle='Flat';$close.ForeColor=[Drawing.Color]::White;$close.BackColor=[Drawing.Color]::FromArgb(19,52,70);$close.Anchor='Bottom,Right';$form.Controls.Add($close)
$script:akiraRemovalExit=0
$script:eraseMode=$false
$body.Text="Se retirará exclusivamente la instalación verificada de AKIRA.\\r\\n\\r\\nSe conservarán tu cuenta, configuración, límites, historial y chats en:\\r\\n$($context.backups)\\r\\n\\r\\nLa operación no cerrará MT5 ni posiciones abiertas, pero AKIRA dejará de supervisarlas.\\r\\n\\r\\nLa verificación, copia y eliminación se harán en segundo plano sin bloquear esta ventana."
$close.Add_Click({$form.Close()})
$script:akiraWorkerProcess=$null
$script:akiraWorkerReport=$null
$script:akiraTimer=New-Object Windows.Forms.Timer
$script:akiraTimer.Interval=350
$script:akiraTimer.Add_Tick({
    if (-not $script:akiraWorkerProcess -or -not $script:akiraWorkerProcess.HasExited) { return }
    $script:akiraTimer.Stop()
    try {
        if (-not (Test-Path -LiteralPath $script:akiraWorkerReport)) {
            throw 'La tarea terminó sin informe. No elimines nada manualmente; comprueba el respaldo.'
        }
        $result=Get-Content -LiteralPath $script:akiraWorkerReport -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($result.status -eq 'UNINSTALLED_ALL') {
            $body.Text='AKIRA y sus datos propios fueron eliminados. Las operaciones que existan en MT5 no se modificaron.'
        } elseif ($result.status -eq 'UNINSTALLED') {
            $body.Text="AKIRA se desinstaló correctamente.`r`n`r`nDatos conservados:`r`n$($result.backup)`r`n`r`nLas operaciones MT5 permanecen en el bróker."
        } elseif ($result.status -eq 'NOT_INSTALLED') {
            $body.Text='No se encontró una instalación verificada de AKIRA. No se borró ningún archivo.'
        } elseif ($result.status -eq 'PARTIAL_CLEANUP') {
            $script:akiraRemovalExit=2
            $body.Text="AKIRA se desactivó, pero Windows bloqueó parte de la limpieza.`r`nRespaldo: $($result.backup)`r`nErrores: $($result.cleanup_errors -join '; ')"
        } else {throw ([string]$result.error)}
    } catch {
        $script:akiraRemovalExit=1
        $body.Text='No terminó la desinstalación. '+$_.Exception.Message
    } finally {
        $script:akiraWorkerProcess.Dispose()
        $script:akiraWorkerProcess=$null
        $close.Enabled=$true;$exit.Enabled=$true;$close.Text='CERRAR';$erase.Enabled=$true
        $form.ControlBox=$true
    }
})
$erase.Add_Click({
    # Two-step explicit confirmation; nothing is deleted on selecting the mode.
    $warning='Se eliminarán de forma DEFINITIVA la configuración, chats, historial, claves, respaldos y versiones de AKIRA. No podrás recuperarlos con el instalador. Las operaciones de MT5 quedarán abiertas sin supervisión. ¿Continuar?'
    $answer=[Windows.Forms.MessageBox]::Show($form,$warning,'ELIMINACIÓN DEFINITIVA','YesNo','Warning')
    if ($answer -ne 'Yes') { return }
    Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction SilentlyContinue
    $confirm=[Microsoft.VisualBasic.Interaction]::InputBox('Para confirmar escribe ELIMINAR AKIRA','Confirmación irreversible','')
    if ($confirm -cne 'ELIMINAR AKIRA') { return }
    $script:eraseMode=$true
    $remove.PerformClick()
})
$remove.Add_Click({
    if (-not $script:eraseMode) {
        $answer=[Windows.Forms.MessageBox]::Show($form,'¿Desinstalar AKIRA conservando todos los datos? AKIRA dejará de gestionar operaciones, sin cerrarlas.','Confirmar desinstalación','YesNo','Question')
        if ($answer -ne 'Yes') { return }
    }
    $remove.Enabled=$false;$erase.Enabled=$false;$close.Enabled=$false;$exit.Enabled=$false;$form.ControlBox=$false
    if ($script:eraseMode) { $body.Text='Retirando exclusivamente archivos de AKIRA y sus datos, sin crear respaldos.' }
    else { $body.Text="Verificando instalaciones y procesos de AKIRA…`r`nGuardando datos con comprobación SHA-256…`r`nRetirando archivos de programa solo después del respaldo." }
    try {
        $script:akiraWorkerReport=Join-Path ([IO.Path]::GetTempPath()) ('AKIRA_UNINSTALL_'+[Guid]::NewGuid().ToString('N')+'.json')
        # The worker must run from a temporary copy, not from a release about to
        # be deleted. This avoids locking its own installation during removal.
        $script:temporaryWorker=Join-Path ([IO.Path]::GetTempPath()) ('AKIRA_UNINSTALL_WORKER_'+[Guid]::NewGuid().ToString('N')+'.ps1')
        Copy-Item -LiteralPath $PSCommandPath -Destination $script:temporaryWorker -Force
        $arguments='-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$script:temporaryWorker+'" -Worker -ResultPath "'+$script:akiraWorkerReport+'"'
        if ($script:eraseMode) { $arguments+=' -EraseAll' }
        $script:akiraWorkerProcess=Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -PassThru -WindowStyle Hidden
        $script:akiraTimer.Start()
    } catch {
        $script:akiraRemovalExit=1;$body.Text='No se pudo iniciar el desinstalador: '+$_.Exception.Message
        $close.Enabled=$true;$exit.Enabled=$true;$form.ControlBox=$true;$remove.Enabled=$true;$erase.Enabled=$true
    }
})
$null=$form.ShowDialog();$script:akiraTimer.Stop();$script:akiraTimer.Dispose();$form.Dispose()
exit $script:akiraRemovalExit
