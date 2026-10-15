param()
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()
$form=New-Object Windows.Forms.Form
$form.Text='AKIRA · Instalador';$form.Size=New-Object Drawing.Size(720,480)
$form.MinimumSize=$form.Size;$form.StartPosition='CenterScreen'
$form.BackColor=[Drawing.Color]::FromArgb(8,14,26)
$form.ForeColor=[Drawing.Color]::FromArgb(224,236,247)
$form.Font=New-Object Drawing.Font('Segoe UI',10)
$form.FormBorderStyle='FixedDialog';$form.MaximizeBox=$false
# Ventana sin franja blanca. Controles de ventana propios y arrastre en el encabezado.
$form.FormBorderStyle='None';$form.ShowIcon=$true
try { $iconPath=Join-Path $PSScriptRoot 'assets\akira.ico';if (Test-Path -LiteralPath $iconPath) { $form.Icon=New-Object Drawing.Icon($iconPath) } } catch {}
$form.Font=New-Object Drawing.Font('Bahnschrift',10)
$top=New-Object Windows.Forms.Panel;$top.Location=New-Object Drawing.Point(0,0)
$top.Size=New-Object Drawing.Size($form.ClientSize.Width,40);$top.BackColor=[Drawing.Color]::FromArgb(13,36,52)
$form.Controls.Add($top)
$brand=New-Object Windows.Forms.Label;$brand.Text='◈  AKIRA  /  SETUP'
$brand.ForeColor=[Drawing.Color]::Turquoise;$brand.Font=New-Object Drawing.Font('Bahnschrift',11,[Drawing.FontStyle]::Bold)
$brand.Location=New-Object Drawing.Point(18,11);$brand.AutoSize=$true;$top.Controls.Add($brand)
$exit=New-Object Windows.Forms.Button;$exit.Text='×';$exit.FlatStyle='Flat'
$exit.FlatAppearance.BorderSize=0;$exit.ForeColor=[Drawing.Color]::White
$exit.BackColor=[Drawing.Color]::FromArgb(13,36,52)
$exit.Location=New-Object Drawing.Point(($form.ClientSize.Width-49),0);$exit.Size=New-Object Drawing.Size(49,40)
$exit.Add_Click({ if (-not $script:child -or $script:child.HasExited) { $form.Close() } });$top.Controls.Add($exit)
try {
 Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public static class AkiraMove { [DllImport("user32.dll")] public static extern bool ReleaseCapture(); [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hwnd,int msg,int wp,int lp); }' -ErrorAction SilentlyContinue
 $drag={param($s,$e) if ($e.Button -eq [Windows.Forms.MouseButtons]::Left) { [AkiraMove]::ReleaseCapture() | Out-Null;[AkiraMove]::SendMessage($form.Handle,0xA1,2,0) | Out-Null }}
 $top.Add_MouseDown($drag);$brand.Add_MouseDown($drag)
} catch {}

$head=New-Object Windows.Forms.Label
$head.Text='AKIRA';$head.Font=New-Object Drawing.Font('Segoe UI',28,[Drawing.FontStyle]::Bold)
$head.ForeColor=[Drawing.Color]::Turquoise;$head.Location=New-Object Drawing.Point(32,54)
$head.Size=New-Object Drawing.Size(380,56);$form.Controls.Add($head)
$sub=New-Object Windows.Forms.Label
$sub.Text='Instalación inteligente  ·  Windows'
$sub.ForeColor=[Drawing.Color]::FromArgb(154,180,205)
$sub.Location=New-Object Drawing.Point(37,113);$sub.Size=New-Object Drawing.Size(590,30);$form.Controls.Add($sub)
$intro=New-Object Windows.Forms.Label
$intro.Text="Detectamos versiones anteriores y recuperamos tu cuenta, historial, chats y preferencias.`r`nLa limpieza segura solo se realiza tras instalar y verificar la versión nueva."
$intro.Location=New-Object Drawing.Point(36,155);$intro.Size=New-Object Drawing.Size(635,63)
$form.Controls.Add($intro)
$state=New-Object Windows.Forms.Label
$state.Text='PREPARADO PARA INSTALAR'
$state.ForeColor=[Drawing.Color]::Turquoise
$state.Location=New-Object Drawing.Point(36,218);$state.Size=New-Object Drawing.Size(620,32)
$form.Controls.Add($state)
$bar=New-Object Windows.Forms.ProgressBar
$bar.Style='Marquee';$bar.MarqueeAnimationSpeed=0
$bar.Location=New-Object Drawing.Point(36,257);$bar.Size=New-Object Drawing.Size(628,12)
$form.Controls.Add($bar)
$detail=New-Object Windows.Forms.TextBox
$detail.ReadOnly=$true;$detail.Multiline=$true;$detail.ScrollBars='Vertical'
$detail.BorderStyle='None';$detail.BackColor=$form.BackColor
$detail.ForeColor=[Drawing.Color]::FromArgb(169,192,211)
$detail.Location=New-Object Drawing.Point(36,283);$detail.Size=New-Object Drawing.Size(628,81)
$detail.Text='El instalador revisa integridad, dependencias, copia segura y acceso directo antes de activar Akira.'
$form.Controls.Add($detail)
$install=New-Object Windows.Forms.Button
$install.Text='INSTALAR AKIRA';$install.FlatStyle='Flat';$install.BackColor=[Drawing.Color]::FromArgb(17,70,88);$install.FlatAppearance.BorderColor=[Drawing.Color]::Turquoise
$install.ForeColor=[Drawing.Color]::White
$install.Location=New-Object Drawing.Point(36,378);$install.Size=New-Object Drawing.Size(628,50)
$form.Controls.Add($install)
$close=New-Object Windows.Forms.Button
$close.Text='CERRAR';$close.FlatStyle='Flat'
$close.ForeColor=$form.ForeColor
$close.Visible=$false;$close.Location=New-Object Drawing.Point(452,378);$close.Size=New-Object Drawing.Size(212,51)
$form.Controls.Add($close)
$script:child=$null
$script:doneTimer=$null
$script:outLog=$null
$script:errLog=$null
$script:lastLength=0
$script:installStartedAt=[DateTime]::MinValue
# Verify the transaction receipt, not merely PowerShell's process exit code.
# Previous versions could display a red failure after INSTALL_HOST_RESULT already
# recorded a fully activated, self-checked application.
function Test-AkiraInstallReceipt {
    try {
        $diagnostics=Join-Path $env:USERPROFILE 'Akira_Diagnostico_Instalacion'
        if (-not (Test-Path -LiteralPath $diagnostics -PathType Container)) { return $false }
        $fresh=@(Get-ChildItem -LiteralPath $diagnostics -Directory -ErrorAction Stop |
            Where-Object { $_.CreationTime -ge $script:installStartedAt.AddSeconds(-5) } |
            Sort-Object CreationTime -Descending)
        foreach ($dir in $fresh) {
            $hostFile=Join-Path $dir.FullName 'INSTALL_HOST_RESULT.json'
            $nativeFile=Join-Path $dir.FullName 'NATIVE_APPLICATION.json'
            $testFile=Join-Path $dir.FullName 'INSTALL_RESULT_AKIRA.json'
            if (-not ((Test-Path -LiteralPath $hostFile) -and (Test-Path -LiteralPath $nativeFile) -and (Test-Path -LiteralPath $testFile))) { continue }
            $hostResult=Get-Content -LiteralPath $hostFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($hostResult.status -ne 'INSTALLED' -or $hostResult.phase -ne 'COMPLETED') { continue }
            $native=Get-Content -LiteralPath $nativeFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $tests=Get-Content -LiteralPath $testFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($native.status -ne 'PASSED' -or $native.self_check.status -ne 'PASSED' -or $tests.status -ne 'PASSED' -or $tests.exit_code -ne 0) { continue }
            $pointer=Join-Path $env:USERPROFILE '.akira_runtime\active_install.json'
            if (-not (Test-Path -LiteralPath $pointer -PathType Leaf)) { continue }
            $active=Get-Content -LiteralPath $pointer -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([IO.Path]::GetFullPath([string]$active.root) -ne [IO.Path]::GetFullPath([string]$hostResult.root)) { continue }
            $exe=Join-Path ([string]$active.root) 'native\AKIRA\AKIRA.exe'
            $shortcut=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Akira.lnk'
            if ((Test-Path -LiteralPath $exe -PathType Leaf) -and (Test-Path -LiteralPath $shortcut -PathType Leaf)) { return $true }
        }
    } catch { return $false }
    return $false
}
$script:timer=New-Object Windows.Forms.Timer
$script:timer.Interval=400
$script:timer.Add_Tick({
    if ($script:outLog -and (Test-Path -LiteralPath $script:outLog)) {
        try {
            $lines=@(Get-Content -LiteralPath $script:outLog -Tail 5 -Encoding UTF8 -ErrorAction Stop)
            if ($lines.Count -gt 0) {
                $detail.Text=($lines -join "`r`n")
                $last=($lines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1)
                if ($last) {$state.Text=([string]$last).Substring(0,[Math]::Min(90,([string]$last).Length))}
            }
        } catch {}
    }
    if (-not $script:child -or -not $script:child.HasExited) { return }
    $script:timer.Stop()
    $bar.MarqueeAnimationSpeed=0
    $bar.Style='Continuous'
    $verified=Test-AkiraInstallReceipt
    $exitCode=$script:child.ExitCode
    # Receipt is authoritative only if the new executable, active pointer,
    # shortcut and native self-check all agree. A zero exit code alone is not.
    if ($verified) {
        $state.Text='AKIRA INSTALADA Y VERIFICADA'
        $state.ForeColor=[Drawing.Color]::FromArgb(78,224,167)
        $bar.Value=100
        $detail.Text="Akira ya se ha instalado y su acceso directo está listo.`r`nEl instalador conservó los datos de tu versión anterior."
        $install.Text='INSTALADA';$install.ForeColor=[Drawing.Color]::White
        # A PowerShell event callback cannot rely on a callback-local timer.
        # A null timer raised an unhandled Windows exception after success.
        if ($null -ne $script:doneTimer) {
            $script:doneTimer.Stop();$script:doneTimer.Dispose()
        }
        $script:doneTimer=New-Object Windows.Forms.Timer
        $script:doneTimer.Interval=2100
        $script:doneTimer.Add_Tick({
            $toClose=$script:doneTimer
            $script:doneTimer=$null
            if ($null -ne $toClose) { $toClose.Stop();$toClose.Dispose() }
            if ($null -ne $form -and -not $form.IsDisposed) { $form.Close() }
        })
        $script:doneTimer.Start()
    } else {
        $state.Text='NO SE COMPLETÓ · REVISAR DIAGNÓSTICO'
        $state.ForeColor=[Drawing.Color]::Salmon
        $bar.Value=0
        $message=''
        if ($script:errLog -and (Test-Path -LiteralPath $script:errLog)) {
            $message=([string](Get-Content -LiteralPath $script:errLog -Tail 5 -ErrorAction SilentlyContinue | Out-String))
        }
        $detail.Text="No hay confirmación verificable de una instalación completa (código de proceso: $exitCode).`r`n$($message)`r`nConsulta Akira_Diagnostico_Instalacion para el error completo."
        # Never repeat an identical failed installation without a changed condition.
        $script:installationFailed=$true
        $install.Enabled=$true;$install.Text='VER DIAGNÓSTICO'
    }
    $script:child.Dispose();$script:child=$null
    $exit.Enabled=$true;$close.Enabled=$true;$form.ControlBox=$true
})
$script:installationFailed=$false
$install.Add_Click({
    if ($script:installationFailed) {
        $folder=Join-Path $env:USERPROFILE 'Akira_Diagnostico_Instalacion'
        if (Test-Path -LiteralPath $folder) { Start-Process explorer.exe -ArgumentList ('"'+$folder+'"') }
        return
    }
    if ($script:child -and -not $script:child.HasExited) { return }
    $install.Enabled=$false
    $exit.Enabled=$false
    $close.Enabled=$false;$form.ControlBox=$false
    $state.Text='REVISANDO TU INSTALACIÓN Y PREPARANDO AKIRA…'
    $bar.Value=0;$bar.Style='Marquee';$bar.MarqueeAnimationSpeed=25
    $detail.Text='No cierres el instalador durante la activación. La versión anterior se mantiene por seguridad.'
    try {
        $jobDir=Join-Path ([IO.Path]::GetTempPath()) ('AKIRA_GUI_'+[Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $jobDir -Force | Out-Null
        $script:installStartedAt=Get-Date
        $script:outLog=Join-Path $jobDir 'INSTALL_STDOUT.log'
        $script:errLog=Join-Path $jobDir 'INSTALL_STDERR.log'
        $command='-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+(Join-Path $PSScriptRoot 'INSTALL_AKIRA.ps1')+'"'
        $script:child=Start-Process -FilePath 'powershell.exe' -ArgumentList $command -PassThru -WindowStyle Hidden -RedirectStandardOutput $script:outLog -RedirectStandardError $script:errLog
        $script:timer.Start()
    } catch {
        $bar.MarqueeAnimationSpeed=0;$bar.Style='Continuous'
        $state.Text='NO SE PUDO INICIAR EL INSTALADOR'
        $detail.Text=$_.Exception.Message
        $install.Enabled=$true;$close.Enabled=$true;$form.ControlBox=$true
    }
})
$close.Add_Click({$form.Close()})
$null=$form.ShowDialog()
if ($null -ne $script:doneTimer) { $script:doneTimer.Stop();$script:doneTimer.Dispose();$script:doneTimer=$null }
$script:timer.Stop();$script:timer.Dispose()
$form.Dispose()
