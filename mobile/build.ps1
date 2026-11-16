param(
    [Parameter(Mandatory)][string]$Sdk,
    [Parameter(Mandatory)][string]$JavaHome,
    [Parameter(Mandatory)][string]$Output,
    [string]$Keystore
)

$ErrorActionPreference = 'Stop'
$env:JAVA_HOME = (Resolve-Path -LiteralPath $JavaHome).Path
$java = Join-Path $env:JAVA_HOME 'bin'
$sdkRoot = (Resolve-Path -LiteralPath $Sdk).Path
$androidJar = Join-Path $sdkRoot 'platforms/android-36/android.jar'
$tools = Join-Path $sdkRoot 'build-tools/36.0.0'
$outputDir = (New-Item -ItemType Directory -Force -Path $Output).FullName
$stage = New-Item -ItemType Directory -Path (Join-Path $outputDir ('compile-' + [Guid]::NewGuid().ToString('N')))
$classes = (New-Item -ItemType Directory -Path (Join-Path $stage.FullName 'classes')).FullName
$dex = (New-Item -ItemType Directory -Path (Join-Path $stage.FullName 'dex')).FullName
$sources = @(Get-ChildItem (Join-Path $PSScriptRoot 'src') -Recurse -Filter '*.java' | ForEach-Object FullName)
& (Join-Path $java 'javac.exe') -encoding UTF-8 --release 8 -classpath $androidJar -d $classes @sources
if ($LASTEXITCODE -ne 0) { throw 'La compilación Java falló.' }
$compiled = @(Get-ChildItem $classes -Recurse -Filter '*.class' | ForEach-Object FullName)
& (Join-Path $tools 'd8.bat') --release --min-api 26 --lib $androidJar --output $dex @compiled
if ($LASTEXITCODE -ne 0) { throw 'La compilación DEX falló.' }
$base = Join-Path $stage.FullName 'base.apk'
& (Join-Path $tools 'aapt2.exe') link --manifest (Join-Path $PSScriptRoot 'AndroidManifest.xml') -I $androidJar -o $base
if ($LASTEXITCODE -ne 0) { throw 'No se pudo empaquetar el manifiesto.' }
Push-Location $dex
try {
    & (Join-Path $tools 'aapt.exe') add $base 'classes.dex'
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo empaquetar el ejecutable de Android.' }
}
finally { Pop-Location }
$unsigned = Join-Path $outputDir 'AKIRA_0.3.0_Android_unsigned.apk'
& (Join-Path $tools 'zipalign.exe') -f 4 $base $unsigned
if ($LASTEXITCODE -ne 0) { throw 'No se pudo alinear el APK.' }
if ($Keystore) {
    $signed = Join-Path $outputDir 'AKIRA_0.3.0_Android.apk'
    $signArgs = @('sign', '--ks', (Resolve-Path -LiteralPath $Keystore).Path)
    if ($env:AKIRA_ANDROID_KEYSTORE_PASSWORD) {
        $signArgs += @('--ks-pass', 'env:AKIRA_ANDROID_KEYSTORE_PASSWORD',
                       '--key-pass', 'env:AKIRA_ANDROID_KEYSTORE_PASSWORD')
    }
    $signArgs += @('--out', $signed, $unsigned)
    & (Join-Path $tools 'apksigner.bat') @signArgs
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo firmar el APK.' }
    & (Join-Path $tools 'apksigner.bat') verify --print-certs $signed
    if ($LASTEXITCODE -ne 0) { throw 'La firma de Android no pasó la comprobación.' }
    Get-FileHash -Algorithm SHA256 -LiteralPath $signed
}
else {
    Get-FileHash -Algorithm SHA256 -LiteralPath $unsigned
}
