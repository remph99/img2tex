$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PYTHONNOUSERSITE = '1'
$condaExe = (Get-Command conda.exe -ErrorAction Stop).Source
$pythonExe = (& $condaExe run -n img2tex python -s -c 'import sys; print(sys.executable)' | Where-Object { $_.Trim() } | Select-Object -Last 1).Trim()
$envRoot = Split-Path $pythonExe
$originalPath = $env:PATH
Push-Location $projectRoot
try {
    # Keep unrelated tools (e.g. Poppler's ICU DLLs) out of dependency resolution.
    $env:PATH = @($envRoot, "$envRoot\Library\bin", "$envRoot\Scripts", "$env:SystemRoot\System32", $env:SystemRoot) -join ';'
    & $pythonExe -s scripts\prepare_release.py
    if ($LASTEXITCODE -ne 0) { throw 'Release metadata generation failed.' }
    & $pythonExe -s -m PyInstaller --noconfirm img2tex.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application packaging failed.' }
    Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $projectRoot 'dist\Img2Tex\README.md')
    $docsTarget = Join-Path $projectRoot 'dist\Img2Tex\docs'
    New-Item -ItemType Directory -Force -Path $docsTarget | Out-Null
    foreach ($documentName in @('validation.md', 'workflow.md', 'environment-versions.txt', 'export-notices.md')) {
        Copy-Item -LiteralPath (Join-Path $projectRoot "docs\$documentName") -Destination $docsTarget
    }
    $modelSource = Join-Path $projectRoot 'models\xiaomi-ocr-0'
    if (Test-Path -LiteralPath (Join-Path $modelSource 'config.json')) {
        $modelTarget = Join-Path $projectRoot 'dist\Img2Tex\models\xiaomi-ocr-0'
        New-Item -ItemType Directory -Force -Path $modelTarget | Out-Null
        Get-ChildItem -LiteralPath $modelSource -File | Copy-Item -Destination $modelTarget
    }
} finally {
    $env:PATH = $originalPath
    Pop-Location
}
