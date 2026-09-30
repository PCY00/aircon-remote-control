<#
Read-only checks for the PCB blog series. Run from any directory with PowerShell.
Checks local Markdown targets and obvious private paths/addresses, not electrical
correctness, remote URL availability, or all possible secrets. Review prose too.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$seriesRoot = Join-Path $repoRoot 'docs/blog/pcb-ir-node'
$expectedFiles = @(
    'README.md',
    '01-requirements-and-parts.md',
    '02-kicad-schematic-review.md',
    '03-pcb-layout-and-routing.md',
    '04-jlcpcb-manufacturing-checks.md'
)
$extraFiles = @(
    'docs/assets/hardware/user-pcb-20260920/README.md',
    'docs/journal/2026-09-22-pcb-blog-series.md'
)
$checkedFiles = @($expectedFiles | ForEach-Object { Join-Path $seriesRoot $_ })
$checkedFiles += @($extraFiles | ForEach-Object { Join-Path $repoRoot $_ })
$utf8Strict = [System.Text.UTF8Encoding]::new($false, $true)
$localLinks = 0
$imageLinks = 0
$issues = [System.Collections.Generic.List[string]]::new()

foreach ($mdPath in $checkedFiles) {
    $label = [System.IO.Path]::GetRelativePath($repoRoot, $mdPath)
    if (-not (Test-Path -LiteralPath $mdPath -PathType Leaf)) {
        $issues.Add("MISSING_DOCUMENT=$label")
        continue
    }
    $content = $utf8Strict.GetString([System.IO.File]::ReadAllBytes($mdPath))
    if ($content -match '(?i)[A-Z]:[\\/]Users[\\/]|\b(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b|-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----') {
        $issues.Add("PRIVATE_PATH_OR_ADDRESS_OR_KEY=$label")
    }
    if (([regex]::Matches($content, '(?m)^```')).Count % 2 -ne 0) {
        $issues.Add("UNBALANCED_CODE_FENCE=$label")
    }
    # Current series uses inline links and plain relative paths without spaces.
    foreach ($match in [regex]::Matches($content, '(!?)\[[^\]\r\n]*\]\(([^\s\)]+)\)')) {
        $target = $match.Groups[2].Value
        if ($target -match '^(?:https?://|mailto:|#)') { continue }
        $target = [System.Uri]::UnescapeDataString(($target -split '#', 2)[0])
        if (-not $target) { continue }
        $resolvedTarget = [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $mdPath) $target))
        $localLinks++
        if ($match.Groups[1].Value -eq '!') { $imageLinks++ }
        if (-not (Test-Path -LiteralPath $resolvedTarget -PathType Leaf)) {
            $issues.Add("BROKEN_LINK=$label -> $target")
        }
    }
}

Write-Output "BLOG_ARTICLES=$($expectedFiles.Count - 1)"
Write-Output "MARKDOWN_FILES_CHECKED=$($checkedFiles.Count)"
Write-Output "LOCAL_LINKS_CHECKED=$localLinks"
Write-Output "IMAGE_EMBEDS_CHECKED=$imageLinks"
Write-Output "ISSUES=$($issues.Count)"
foreach ($issue in $issues) { Write-Output $issue }
if ($issues.Count -gt 0) { exit 1 }
Write-Output 'BLOG_STRUCTURE_CHECK=PASS'
Write-Output 'SCOPE=Local links, UTF-8, code fences, obvious private paths/addresses/keys; not an electrical or exhaustive security audit'
