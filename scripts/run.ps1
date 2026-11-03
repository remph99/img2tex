param([ValidateSet('full','cpuonly')][string]$Edition = 'cpuonly')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$environmentName = if ($Edition -eq 'cpuonly') { 'img2tex-cpuonly' } else { 'img2tex' }
& conda.exe run --no-capture-output --name $environmentName python -s -m img2tex
