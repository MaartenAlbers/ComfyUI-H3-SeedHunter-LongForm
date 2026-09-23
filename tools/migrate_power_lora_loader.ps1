$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$workflowPath = Join-Path $root 'H3_SeedHunter_Long_Form_Video_v1.4_DEV.json'
$workflow = Get-Content -LiteralPath $workflowPath -Raw | ConvertFrom-Json

if ($workflow.nodes | Where-Object { $_.type -eq 'Power Lora Loader (rgthree)' }) {
    Write-Output 'Power Lora Loader already present; no changes made.'
    exit 0
}

$attention = $workflow.nodes | Where-Object { [int]$_.id -eq 1756 }
$turbo = $workflow.nodes | Where-Object { [int]$_.id -eq 977 }
$oldLink = $workflow.links | Where-Object { [int]$_[0] -eq 822 }
if (-not $attention -or -not $turbo -or -not $oldLink) {
    throw 'Expected H3 attention-to-turbo model chain was not found.'
}
if ([int]$oldLink[1] -ne 1756 -or [int]$oldLink[3] -ne 977) {
    throw 'Link 822 no longer connects the expected attention and turbo nodes.'
}

$nodeId = [int]$workflow.last_node_id + 1
$newLinkId = [int]$workflow.last_link_id + 1

$powerLora = [pscustomobject]@{
    id = $nodeId
    type = 'Power Lora Loader (rgthree)'
    pos = @(-1600.0, -430.0)
    size = @(420.0, 180.0)
    flags = [pscustomobject]@{}
    order = [int](($workflow.nodes | Measure-Object -Property order -Maximum).Maximum + 1)
    mode = 0
    inputs = @(
        [pscustomobject]@{ dir=3; name='model'; type='MODEL'; link=822 },
        [pscustomobject]@{ dir=3; name='clip'; type='CLIP'; link=$null }
    )
    outputs = @(
        [pscustomobject]@{ dir=4; name='MODEL'; shape=3; type='MODEL'; links=@($newLinkId) },
        [pscustomobject]@{ dir=4; name='CLIP'; shape=3; type='CLIP'; links=$null }
    )
    title = 'OPTIONAL CREATIVE H3 LORAS — add as many as needed'
    properties = [pscustomobject]@{
        cnr_id = 'rgthree-comfy'
        'Show Strengths' = 'Single Strength'
        Match = ''
        ue_properties = [pscustomobject]@{
            widget_ue_connectable = [pscustomobject]@{}
            input_ue_unconnectable = [pscustomobject]@{}
            version = '7.8'
        }
    }
    widgets_values = @(
        [pscustomobject]@{},
        [pscustomobject]@{ type='PowerLoraLoaderHeaderWidget' },
        [pscustomobject]@{},
        ''
    )
    color = '#332922'
    bgcolor = '#593930'
}

# Keep the existing link id on the upstream half so references remain stable.
$oldLink[3] = $nodeId
$oldLink[4] = 0
($turbo.inputs | Where-Object { $_.name -eq 'model' }).link = $newLinkId
$workflow.links = @($workflow.links) + ,@($newLinkId, $nodeId, 0, 977, 0, 'MODEL')
$workflow.nodes = @($workflow.nodes) + $powerLora
$workflow.last_node_id = $nodeId
$workflow.last_link_id = $newLinkId
$workflow.revision = [int]$workflow.revision + 1

$workflow | ConvertTo-Json -Depth 100 -Compress | Set-Content -LiteralPath $workflowPath -Encoding utf8NoBOM
Write-Output "Added rgthree Power Lora Loader as node $nodeId with model link $newLinkId."
