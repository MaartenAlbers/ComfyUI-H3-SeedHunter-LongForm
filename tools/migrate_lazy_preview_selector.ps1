param(
    [Parameter(Mandatory = $true)]
    [string]$WorkflowPath
)

$ErrorActionPreference = 'Stop'

$resolved = (Resolve-Path -LiteralPath $WorkflowPath).Path
$content = [System.IO.File]::ReadAllText($resolved)
$old = '"id":2627,"type":"ImpactSwitch"'
$new = '"id":2627,"type":"H3SeedHunterLazyPreviewSelect"'
$matches = ([regex]::Matches($content, [regex]::Escape($old))).Count
if ($matches -ne 1) {
    throw "Expected exactly one old preview selector, found $matches."
}
$updated = $content.Replace($old, $new)
[System.IO.File]::WriteAllText($resolved, $updated, [System.Text.UTF8Encoding]::new($false))
Write-Host "Migrated preview selector in $resolved"
