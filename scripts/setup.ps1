param([ValidateSet('cpu','cuda')][string]$TorchBuild = 'cpu')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$condaExe = (Get-Command conda.exe -ErrorAction Stop).Source
$env:PYTHONNOUSERSITE = '1'
$condaInfo = (& $condaExe env list --json | ConvertFrom-Json)
if (-not ($condaInfo.envs | Where-Object { (Split-Path $_ -Leaf) -eq 'img2tex' })) {
    & $condaExe env create --file (Join-Path $projectRoot 'environment.yml') --yes
    if ($LASTEXITCODE -ne 0) { throw 'Conda environment creation failed.' }
}
& $condaExe env config vars set --name img2tex PYTHONNOUSERSITE=1
$pythonExe = (& $condaExe run -n img2tex python -s -c 'import sys; print(sys.executable)' | Where-Object { $_.Trim() } | Select-Object -Last 1).Trim()
$index = if ($TorchBuild -eq 'cuda') { 'https://download.pytorch.org/whl/cu130' } else { 'https://download.pytorch.org/whl/cpu' }
& $pythonExe -s -m pip install --upgrade --force-reinstall 'torch==2.14.0' 'torchvision==0.29.0' --index-url $index
if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed.' }
Push-Location $projectRoot
try {
    & $pythonExe -s -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Application dependency installation failed.' }
    & $pythonExe -s -m img2tex --check-device
} finally { Pop-Location }
