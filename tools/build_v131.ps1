$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root 'H3_SeedHunter_Long_Form_Video_v1.3.json'
$target = Join-Path $root 'H3_SeedHunter_Long_Form_Video_v1.3.1.json'
$workflow = Get-Content -LiteralPath $source -Raw | ConvertFrom-Json
$existing = $workflow.nodes | Where-Object { $_.title -like '*SAVE SINGLE PASS CONTEXT*' }
if ($existing) { throw 'The source already contains a single-pass context save node.' }
$template = $workflow.nodes | Where-Object { $_.id -eq 2578 }
if (-not $template) { throw 'Final context save template node 2578 was not found.' }
$preview = $workflow.nodes | Where-Object { $_.id -eq 2620 }
if (-not $preview) { throw 'Preview 1 sampler node 2620 was not found.' }
$newNodeId = [int]$workflow.last_node_id + 1
$latentLinkId = [int]$workflow.last_link_id + 1
$clipLinkId = $latentLinkId + 1
$node = $template | ConvertTo-Json -Depth 100 | ConvertFrom-Json
$node.id = $newNodeId
$node.pos = @([double]700, [double]1815)
$node.mode = 4
$node.title = 'SAVE SINGLE PASS CONTEXT — AUTO-ENABLED WITH SINGLE PASS'
$node.inputs[0].link = $latentLinkId
$node.inputs[2].link = $clipLinkId
$node.widgets_values[0] = 'h3_resume/seedhunter_1_3_1/clip'
$preview.outputs[0].links = @($preview.outputs[0].links) + $latentLinkId
$clipNumber = $workflow.nodes | Where-Object { $_.id -eq 2642 }
$clipNumber.outputs[0].links = @($clipNumber.outputs[0].links) + $clipLinkId
$workflow.nodes = @($workflow.nodes) + $node
$workflow.links = @($workflow.links) + ,@($latentLinkId, 2620, 0, $newNodeId, 0, 'LATENT') + ,@($clipLinkId, 2642, 0, $newNodeId, 2, 'INT')
$workflow.last_node_id = $newNodeId
$workflow.last_link_id = $clipLinkId
$workflow.revision = [int]$workflow.revision + 1
$workflow.extra.h3_longform_seedhunter.release_version = '1.3.1'
$workflow | ConvertTo-Json -Depth 100 -Compress | Set-Content -LiteralPath $target -Encoding utf8NoBOM
Write-Output $target
