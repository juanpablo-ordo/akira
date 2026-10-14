param()
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$form=New-Object System.Windows.Forms.Form
$form.Text='AKIRA 16.3.2';$form.Size=New-Object System.Drawing.Size(610,340)
$form.StartPosition='CenterScreen';$form.FormBorderStyle='FixedDialog';$form.MaximizeBox=$false
$form.BackColor=[System.Drawing.Color]::FromArgb(9,17,29)
$form.ForeColor=[System.Drawing.Color]::FromArgb(219,235,246)
$form.Font=New-Object System.Drawing.Font('Segoe UI',10)
$title=New-Object System.Windows.Forms.Label
$title.Text='AKIRA 16.3.2';$title.Location=New-Object System.Drawing.Point(26,22);$title.AutoSize=$true
$title.Font=New-Object System.Drawing.Font('Segoe UI',22,[System.Drawing.FontStyle]::Bold)
$title.ForeColor=[System.Drawing.Color]::Turquoise;$form.Controls.Add($title)
$description=New-Object System.Windows.Forms.Label
$description.Text="Elige qué quieres hacer antes de instalar.`r`nLa desinstalación conserva tus datos y funciona aunque AKIRA no abra."
$description.Location=New-Object System.Drawing.Point(28,83);$description.Size=New-Object System.Drawing.Size(540,74);$form.Controls.Add($description)
$install=New-Object System.Windows.Forms.Button
$install.Text='INSTALAR / ACTUALIZAR';$install.Location=New-Object System.Drawing.Point(28,166);$install.Size=New-Object System.Drawing.Size(260,49)
$install.FlatStyle='Flat';$install.ForeColor=[System.Drawing.Color]::Turquoise;$install.DialogResult='OK';$form.Controls.Add($install)
$remove=New-Object System.Windows.Forms.Button
$remove.Text='DESINSTALAR AKIRA';$remove.Location=New-Object System.Drawing.Point(304,166);$remove.Size=New-Object System.Drawing.Size(260,49)
$remove.FlatStyle='Flat';$remove.ForeColor=[System.Drawing.Color]::Salmon;$remove.DialogResult='Yes';$form.Controls.Add($remove)
$cancel=New-Object System.Windows.Forms.Button
$cancel.Text='CERRAR';$cancel.Location=New-Object System.Drawing.Point(424,238);$cancel.Size=New-Object System.Drawing.Size(140,35)
$cancel.FlatStyle='Flat';$cancel.DialogResult='Cancel';$form.Controls.Add($cancel);$form.CancelButton=$cancel
$choice=$form.ShowDialog();$form.Dispose()
if ($choice -eq 'OK') {
    & (Join-Path $PSScriptRoot 'INSTALL_AKIRA.ps1')
} elseif ($choice -eq 'Yes') {
    & (Join-Path $PSScriptRoot 'DESINSTALAR_AKIRA.ps1')
} else { Write-Host 'Operación cancelada. No se hizo ningún cambio.' }
