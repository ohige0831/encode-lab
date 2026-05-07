<#
.SYNOPSIS
    Build EncodeLab.exe and assemble the distributable folder.

.DESCRIPTION
    1. Optionally cleans build/ and dist/.
    2. Runs PyInstaller with EncodeLab.spec.
    3. Copies ffmpeg.exe / ffprobe.exe into dist\EncodeLab\ffmpeg\
       (required by main.py:_prepend_bundled_ffmpeg).
    4. Verifies the output and prints a summary.

    ffmpeg source priority:
      1. encode-lab\vendor\ffmpeg\ffmpeg.exe   (preferred — reproducible)
      2. System PATH ffmpeg (convenience — copies the installed binary)
      If neither is found, the step is skipped with a warning.

.PARAMETER Clean
    Delete build\ and dist\ before building.

.PARAMETER SkipFfmpeg
    Skip the ffmpeg copy step entirely.

.EXAMPLE
    .\scripts\build_exe.ps1
    .\scripts\build_exe.ps1 -Clean
    .\scripts\build_exe.ps1 -SkipFfmpeg
#>

param(
    [switch]$Clean,
    [switch]$SkipFfmpeg
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$scriptDir  = $PSScriptRoot                                   # …\scripts\
$projectDir = Split-Path $scriptDir -Parent                   # …\Encode_Lab\
$appDir     = Join-Path $projectDir "encode-lab"              # …\encode-lab\
$vendorDir  = Join-Path $appDir "vendor\ffmpeg"               # …\vendor\ffmpeg\
$distExe    = Join-Path $appDir "dist\EncodeLab\EncodeLab.exe"
$ffmpegDest = Join-Path $appDir "dist\EncodeLab\ffmpeg"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  EncodeLab — build script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  App dir : $appDir"
Write-Host "  Vendor  : $vendorDir"
Write-Host "  Output  : $(Split-Path $distExe -Parent)"
Write-Host ""

# ---------------------------------------------------------------------------
# 0. Validate environment
# ---------------------------------------------------------------------------
Write-Host "[0] Validating environment..." -ForegroundColor Yellow

if (-not (Test-Path $appDir)) {
    Write-Error "encode-lab/ not found at $appDir"
    exit 1
}

$pyInstaller = python -m PyInstaller --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller not found. Run: pip install pyinstaller"
    exit 1
}
Write-Host "    PyInstaller : $($pyInstaller.ToString().Trim())"

$pyVer = python --version 2>&1
Write-Host "    Python      : $($pyVer.ToString().Trim())"
Write-Host "    OK" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 1. Clean (optional)
# ---------------------------------------------------------------------------
if ($Clean) {
    Write-Host ""
    Write-Host "[1] Cleaning build/ and dist/..." -ForegroundColor Yellow
    @("$appDir\build", "$appDir\dist") | ForEach-Object {
        if (Test-Path $_) {
            Remove-Item $_ -Recurse -Force
            Write-Host "    Removed: $_"
        }
    }
    Write-Host "    OK" -ForegroundColor Green
} else {
    Write-Host "[1] Skipping clean (use -Clean to wipe build/ and dist/)"
}

# ---------------------------------------------------------------------------
# 2. PyInstaller build
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[2] Running PyInstaller..." -ForegroundColor Yellow

Push-Location $appDir
try {
    # Temporarily suppress Stop on stderr so PyInstaller's INFO/WARNING output
    # to stderr doesn't abort the script — rely on exit code instead.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    python -m PyInstaller --noconfirm --clean EncodeLab.spec
    $pyiExit = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($pyiExit -ne 0) {
        Write-Error "PyInstaller exited with code $pyiExit"
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host "    OK" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 3. Copy ffmpeg / ffprobe into dist\EncodeLab\ffmpeg\
# ---------------------------------------------------------------------------
Write-Host ""
if ($SkipFfmpeg) {
    Write-Host "[3] Skipping ffmpeg copy (-SkipFfmpeg)" -ForegroundColor Yellow
} else {
    Write-Host "[3] Copying ffmpeg binaries..." -ForegroundColor Yellow

    # Shim threshold: Chocolatey shims are ~0.4 MB; real ffmpeg is 50+ MB.
    $shimThresholdMB = 5

    function Resolve-RealBinary([string]$path) {
        <#
        Returns the real executable path, bypassing Chocolatey shims.
        Shims are tiny launchers (~0.4 MB) inside C:\ProgramData\chocolatey\bin\.
        The real binary lives at chocolatey\lib\<pkg>\tools\**\<name>.exe.
        If the provided path is not a shim, it is returned unchanged.
        #>
        if (-not (Test-Path $path)) { return $null }

        $sizeMB = (Get-Item $path).Length / 1MB
        if ($sizeMB -ge $shimThresholdMB) { return $path }  # already real

        Write-Host ("    Shim detected ({0:N1} MB): {1}" -f $sizeMB, $path) -ForegroundColor Yellow

        $name    = [System.IO.Path]::GetFileName($path)   # e.g. ffmpeg.exe
        $pkgName = [System.IO.Path]::GetFileNameWithoutExtension($name)  # ffmpeg

        # Walk chocolatey\lib\<pkgName>\tools\**\<name>
        # ffprobe ships inside the ffmpeg package, so also search lib\ffmpeg\ as fallback.
        $searchPkgs = @($pkgName, "ffmpeg") | Select-Object -Unique
        foreach ($pkg in $searchPkgs) {
            $chocoLib = "C:\ProgramData\chocolatey\lib\$pkg"
            if (Test-Path $chocoLib) {
                $candidates = Get-ChildItem -Path $chocoLib -Recurse -Filter $name -ErrorAction SilentlyContinue |
                              Where-Object { $_.Length / 1MB -ge $shimThresholdMB } |
                              Sort-Object Length -Descending
                if ($candidates) {
                    $real = $candidates[0].FullName
                    Write-Host ("    Resolved real binary: {0} ({1:N1} MB)" -f $real, ($candidates[0].Length / 1MB)) -ForegroundColor Cyan
                    return $real
                }
            }
        }

        Write-Host "    WARNING: Could not resolve real binary from Chocolatey lib. Shim will be used." -ForegroundColor Red
        Write-Host "    To fix: copy the real $name to encode-lab\vendor\ffmpeg\"
        return $path  # fall back to shim with warning already printed
    }

    $ffSrcFF  = $null   # resolved path for ffmpeg.exe
    $ffSrcFFP = $null   # resolved path for ffprobe.exe

    # Priority 1: vendor/ffmpeg/
    $vendorFF  = Join-Path $vendorDir "ffmpeg.exe"
    $vendorFFP = Join-Path $vendorDir "ffprobe.exe"
    if ((Test-Path $vendorFF) -and (Test-Path $vendorFFP)) {
        Write-Host "    Source: vendor/ffmpeg/"
        $ffSrcFF  = Resolve-RealBinary $vendorFF
        $ffSrcFFP = Resolve-RealBinary $vendorFFP
    }

    # Priority 2: system PATH
    if (-not $ffSrcFF) {
        $sysFF  = (where.exe ffmpeg  2>$null) -split "`n" | Select-Object -First 1
        $sysFFP = (where.exe ffprobe 2>$null) -split "`n" | Select-Object -First 1
        if ($sysFF -and $sysFFP -and (Test-Path $sysFF) -and (Test-Path $sysFFP)) {
            Write-Host "    Source: system PATH"
            $ffSrcFF  = Resolve-RealBinary $sysFF.Trim()
            $ffSrcFFP = Resolve-RealBinary $sysFFP.Trim()
        }
    }

    if ($ffSrcFF -and $ffSrcFFP) {
        if (-not (Test-Path $ffmpegDest)) {
            New-Item -ItemType Directory -Force $ffmpegDest | Out-Null
        }

        Copy-Item $ffSrcFF  (Join-Path $ffmpegDest "ffmpeg.exe")  -Force
        Copy-Item $ffSrcFFP (Join-Path $ffmpegDest "ffprobe.exe") -Force

        $ffSize  = (Get-Item (Join-Path $ffmpegDest "ffmpeg.exe")).Length / 1MB
        $ffpSize = (Get-Item (Join-Path $ffmpegDest "ffprobe.exe")).Length / 1MB
        Write-Host ("    ffmpeg.exe  : {0:N1} MB" -f $ffSize)
        Write-Host ("    ffprobe.exe : {0:N1} MB" -f $ffpSize)

        if ($ffSize -lt $shimThresholdMB -or $ffpSize -lt $shimThresholdMB) {
            Write-Host "    WARNING: One or both binaries appear to be shims." -ForegroundColor Red
            Write-Host "    The built package may not work on machines without Chocolatey."
            Write-Host "    Copy real ffmpeg.exe + ffprobe.exe (50+ MB each) to:"
            Write-Host "      encode-lab\vendor\ffmpeg\"
        } else {
            Write-Host "    OK" -ForegroundColor Green
        }
    } else {
        Write-Host "    WARNING: ffmpeg not found in vendor/ or system PATH." -ForegroundColor Yellow
        Write-Host "    The app will start but cannot convert without ffmpeg."
        Write-Host "    Manually copy ffmpeg.exe + ffprobe.exe to:"
        Write-Host "      $ffmpegDest"
    }
}

# ---------------------------------------------------------------------------
# 4. Verify output
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[4] Verifying output..." -ForegroundColor Yellow

$ok = $true

function Check-Path($label, $path) {
    if (Test-Path $path) {
        $size = (Get-Item $path).Length / 1MB
        Write-Host ("    OK  {0,-28} ({1:N1} MB)" -f $label, $size) -ForegroundColor Green
    } else {
        Write-Host ("    MISSING  {0}" -f $label) -ForegroundColor Red
        $script:ok = $false
    }
}

Check-Path "EncodeLab.exe"        $distExe
Check-Path "ffmpeg/ffmpeg.exe"    (Join-Path $ffmpegDest "ffmpeg.exe")
Check-Path "ffmpeg/ffprobe.exe"   (Join-Path $ffmpegDest "ffprobe.exe")

$internalDir = Join-Path (Split-Path $distExe -Parent) "_internal"
if (Test-Path $internalDir) {
    $internalCount = (Get-ChildItem $internalDir -Recurse -File).Count
    Write-Host "    OK  _internal/  ($internalCount files)" -ForegroundColor Green
} else {
    Write-Host "    MISSING  _internal/" -ForegroundColor Red
    $ok = $false
}

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan

if ($ok) {
    $distDir  = Split-Path $distExe -Parent
    $zipHint  = "Compress-Archive -Path '$distDir\*' -DestinationPath 'EncodeLab.zip'"
    Write-Host "  BUILD SUCCEEDED" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Executable : $distExe"
    Write-Host "  ffmpeg dir : $ffmpegDest"
    Write-Host ""
    Write-Host "  To test without system ffmpeg on PATH:"
    Write-Host "    `$env:PATH = `$env:PATH -replace [regex]::Escape((Split-Path (where.exe ffmpeg) -Parent)) + ';', ''"
    Write-Host "    & '$distExe'"
    Write-Host ""
    Write-Host "  To package for distribution:"
    Write-Host "    $zipHint"
} else {
    Write-Host "  BUILD INCOMPLETE — see warnings above" -ForegroundColor Red
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
