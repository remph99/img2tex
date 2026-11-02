param(
    [ValidateSet('installer', 'portable')][string]$Edition = 'portable',
    [string]$Directory = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'
$folder = (Resolve-Path -LiteralPath $Directory).Path
$name = if ($Edition -eq 'installer') { 'Img2Tex-1.0.0-Windows-x64-Setup.exe' } else { 'Img2Tex-1.0.0-Windows-x64-Portable.zip' }
$output = Join-Path $folder $name
if (Test-Path -LiteralPath $output) { throw "Output already exists; preserved: $output" }

function Read-Hashes([string]$path) {
    $hashes = @{}
    foreach ($line in Get-Content -LiteralPath $path) {
        if ($line -match '^([0-9a-fA-F]{64})  (.+)$') { $hashes[$Matches[2]] = $Matches[1] }
    }
    return $hashes
}
$wholeHashes = Read-Hashes (Join-Path $folder 'SHA256SUMS.txt')
$partHashes = Read-Hashes (Join-Path $folder 'SHA256SUMS.parts.txt')
if (-not $wholeHashes.ContainsKey($name)) { throw "Missing full-file checksum: $name" }
$pattern = '^' + [regex]::Escape($name) + '\.part(\d+)$'
$parts = @($partHashes.Keys | Where-Object { $_ -match $pattern } |
    Sort-Object { [int]([regex]::Match($_, $pattern).Groups[1].Value) })
if ($parts.Count -eq 0) { throw "No parts listed for: $name" }
for ($index = 0; $index -lt $parts.Count; $index++) {
    $number = [int]([regex]::Match($parts[$index], $pattern).Groups[1].Value)
    if ($number -ne $index + 1) { throw "Part numbering is incomplete for: $name" }
}
foreach ($part in $parts) {
    if (-not $partHashes.ContainsKey($part)) { throw "Missing part checksum: $part" }
    $actual = (Get-FileHash -LiteralPath (Join-Path $folder $part) -Algorithm SHA256).Hash
    if ($actual -ne $partHashes[$part]) { throw "Part checksum mismatch; download again: $part" }
}

$temporary = "$output.assembling-$([guid]::NewGuid().ToString('N'))"
$stream = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
try {
    foreach ($part in $parts) {
        $source = [IO.File]::OpenRead((Join-Path $folder $part))
        try { $source.CopyTo($stream) } finally { $source.Dispose() }
    }
} finally { $stream.Dispose() }
$actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash
if ($actual -ne $wholeHashes[$name]) { throw "Full checksum mismatch; incomplete output retained for inspection: $temporary" }
[IO.File]::Move($temporary, $output)
Write-Output "Verified and assembled: $output"
