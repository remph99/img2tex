param([ValidateSet('full','cpuonly')][string]$Edition = 'full')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PYTHONNOUSERSITE = '1'
$condaExe = (Get-Command conda.exe -ErrorAction Stop).Source
$environmentName = if ($Edition -eq 'cpuonly') { 'img2tex-cpuonly' } else { 'img2tex' }
$pythonExe = (& $condaExe run -n $environmentName python -s -c 'import sys; print(sys.executable)' | Where-Object { $_.Trim() } | Select-Object -Last 1).Trim()
$envRoot = Split-Path $pythonExe
$originalPath = $env:PATH
$originalEdition = $env:IMG2TEX_EDITION
$runtimeRoot = Join-Path $projectRoot "dist\$Edition\Img2Tex"
Push-Location $projectRoot
try {
    # Keep unrelated tools (e.g. Poppler's ICU DLLs) out of dependency resolution.
    $env:PATH = @($envRoot, "$envRoot\Library\bin", "$envRoot\Scripts", "$env:SystemRoot\System32", $env:SystemRoot) -join ';'
    & $pythonExe -s scripts\prepare_release.py
    if ($LASTEXITCODE -ne 0) { throw 'Release metadata generation failed.' }
    $env:IMG2TEX_EDITION = $Edition
    & $pythonExe -s -m PyInstaller --noconfirm --clean --workpath "build\pyinstaller-$Edition" --distpath "dist\$Edition" img2tex.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application packaging failed.' }
    & $pythonExe -s -c 'import json,sys,torch,torchvision; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps(dict(edition=sys.argv[2],torch=torch.__version__,torchvision=torchvision.__version__,cuda_runtime=torch.version.cuda)),encoding="utf8")' (Join-Path $runtimeRoot 'img2tex-runtime.json') $Edition
    if ($LASTEXITCODE -ne 0) { throw 'Runtime metadata generation failed.' }
    Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $runtimeRoot 'README.md')
    $docsTarget = Join-Path $runtimeRoot 'docs'
    New-Item -ItemType Directory -Force -Path $docsTarget | Out-Null
    foreach ($documentName in @('validation.md', 'workflow.md', 'environment-versions.txt', 'export-notices.md')) {
        Copy-Item -LiteralPath (Join-Path $projectRoot "docs\$documentName") -Destination $docsTarget
    }
    $modelSource = Join-Path $projectRoot 'models\xiaomi-ocr-0'
    if (Test-Path -LiteralPath (Join-Path $modelSource 'config.json')) {
        $modelTarget = Join-Path $runtimeRoot 'models\xiaomi-ocr-0'
        New-Item -ItemType Directory -Force -Path $modelTarget | Out-Null
        & $pythonExe -s -c 'import sys,shutil; from pathlib import Path; from img2tex.model_setup import MODEL_FILES; source,target=map(Path,sys.argv[1:]); [shutil.copy2(source/name,target/name) for name in MODEL_FILES+["README.md","LICENSE","img2tex-model.json"]]' $modelSource $modelTarget
        if ($LASTEXITCODE -ne 0) { throw 'Model staging failed.' }
    }
} finally {
    $env:PATH = $originalPath
    $env:IMG2TEX_EDITION = $originalEdition
    Pop-Location
}
