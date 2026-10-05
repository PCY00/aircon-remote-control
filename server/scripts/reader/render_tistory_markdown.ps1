param(
    [Parameter(Mandatory=$true)][string]$InputDirectory,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$utf8 = [System.Text.UTF8Encoding]::new($false)
[System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
foreach ($file in Get-ChildItem -LiteralPath $InputDirectory -Filter '*.md') {
    $body = (ConvertFrom-Markdown -LiteralPath $file.FullName).Html
    [System.IO.File]::WriteAllText((Join-Path $OutputDirectory ($file.BaseName + '.html')), $body, $utf8)
}
