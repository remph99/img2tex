$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = Join-Path $projectRoot 'src'
& conda.exe run --no-capture-output --name img2tex python -s -m img2tex
