$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root 'H3_SeedHunter_Long_Form_Video_v1.3.1.json'
$target = Join-Path $root 'H3_SeedHunter_Long_Form_Video_v1.4_DEV.json'
$workflow = Get-Content -LiteralPath $source -Raw | ConvertFrom-Json

if ($workflow.nodes | Where-Object type -eq 'H3SeedHunterProject') {
    throw 'The source workflow already contains an H3SeedHunterProject node.'
}

$nodeId = [int]$workflow.last_node_id + 1
$contextNodeId = $nodeId + 1
$clipDisplayNodeId = $contextNodeId + 1
$order = (($workflow.nodes | Measure-Object -Property order -Maximum).Maximum + 1)
$project = [pscustomobject]@{
    id = $nodeId
    type = 'H3SeedHunterProject'
    pos = @(-3460.0, -700.0)
    size = @(620.0, 340.0)
    flags = [pscustomobject]@{}
    order = $order
    mode = 0
    inputs = @(
        [pscustomobject]@{ localized_name='project_name'; name='project_name'; type='STRING'; widget=[pscustomobject]@{name='project_name'}; link=$null },
        [pscustomobject]@{ localized_name='action'; name='action'; type='COMBO'; widget=[pscustomobject]@{name='action'}; link=$null }
    )
    outputs = @(
        [pscustomobject]@{ localized_name='project_path'; name='project_path'; type='STRING'; links=$null },
        [pscustomobject]@{ localized_name='project_id'; name='project_id'; type='STRING'; links=$null },
        [pscustomobject]@{ localized_name='project_revision'; name='project_revision'; type='INT'; links=$null },
        [pscustomobject]@{ localized_name='project_token'; name='project_token'; type='STRING'; links=$null },
        [pscustomobject]@{ localized_name='next_clip_index'; name='next_clip_index'; type='INT'; links=$null },
        [pscustomobject]@{ localized_name='previous_clip_video'; name='previous_clip_video'; type='STRING'; links=$null },
        [pscustomobject]@{ localized_name='previous_context_latent'; name='previous_context_latent'; type='STRING'; links=$null },
        [pscustomobject]@{ localized_name='master_audio'; name='master_audio'; type='STRING'; links=$null },
        [pscustomobject]@{ localized_name='project_status'; name='project_status'; type='STRING'; links=$null }
    )
    title = 'PROJECT — CREATE OR LOAD LONG-FORM STATE'
    properties = [pscustomobject]@{
        'Node name for S&R' = 'H3SeedHunterProject'
        seedhunter_project = $null
        ue_properties = [pscustomobject]@{ widget_ue_connectable=[pscustomobject]@{}; input_ue_unconnectable=[pscustomobject]@{}; version='7.8' }
    }
    widgets_values = @('my_first_project', 'load project')
    widgets_values_named = [pscustomobject]@{ project_name='my_first_project'; action='load project' }
    color = '#346b6d'
    bgcolor = '#203b3c'
}

$workflow.nodes = @($workflow.nodes) + $project

$linkId = [int]$workflow.last_link_id
$contextPathLink = ++$linkId
$projectTokenLink = ++$linkId
$contextLatentLink = ++$linkId
$sourceVideoLink = ++$linkId
$projectClipLink = ++$linkId

$contextLoader = [pscustomobject]@{
    id = $contextNodeId
    type = 'H3SeedHunterProjectContext'
    pos = @(-1810.0, 1460.0)
    size = @(520.0, 130.0)
    flags = [pscustomobject]@{}
    order = $order + 1
    mode = 0
    inputs = @(
        [pscustomobject]@{ localized_name='latent_path'; name='latent_path'; type='STRING'; link=$contextPathLink },
        [pscustomobject]@{ localized_name='project_token'; name='project_token'; type='STRING'; link=$projectTokenLink }
    )
    outputs = @(
        [pscustomobject]@{ localized_name='context_latent'; name='context_latent'; type='LATENT'; links=@($contextLatentLink) }
    )
    title = 'PROJECT — LOAD PREVIOUS ACCEPTED AV LATENT'
    properties = [pscustomobject]@{
        'Node name for S&R' = 'H3SeedHunterProjectContext'
        ue_properties = [pscustomobject]@{ widget_ue_connectable=[pscustomobject]@{}; input_ue_unconnectable=[pscustomobject]@{}; version='7.8' }
    }
    widgets_values = $null
    color = '#346b6d'
    bgcolor = '#203b3c'
}

$clipDisplay = [pscustomobject]@{
    id = $clipDisplayNodeId
    type = 'H3SeedHunterProjectClipIndex'
    pos = @(-2370.0, 1000.0)
    size = @(530.0, 100.0)
    flags = [pscustomobject]@{}
    order = $order + 2
    mode = 0
    inputs = @(
        [pscustomobject]@{ localized_name='clip_index'; name='clip_index'; type='INT'; link=$projectClipLink }
    )
    outputs = @(
        [pscustomobject]@{ localized_name='clip_index'; name='clip_index'; type='INT'; links=@(1649,1650,31281) }
    )
    title = 'CURRENT PROJECT CLIP — LOAD A PROJECT'
    properties = [pscustomobject]@{
        'Node name for S&R' = 'H3SeedHunterProjectClipIndex'
        ue_properties = [pscustomobject]@{ widget_ue_connectable=[pscustomobject]@{}; input_ue_unconnectable=[pscustomobject]@{}; version='7.8' }
    }
    widgets_values = $null
    color = '#346b6d'
    bgcolor = '#203b3c'
}

$avContext = $workflow.nodes | Where-Object id -eq 201
$avContext.inputs = @($avContext.inputs) + [pscustomobject]@{
    localized_name='context_latent'; name='context_latent'; shape=7
    type='LATENT'; link=$contextLatentLink
}

$sourceNode = $workflow.nodes | Where-Object id -eq 2616
($sourceNode.inputs | Where-Object name -eq 'video').link = $sourceVideoLink

# Project state becomes authoritative for every clip-index consumer. The old
# PrimitiveInt remains as a visible status/controller mirror only.
$clipLinks = @(1649, 1650, 31281)
foreach ($id in $clipLinks) {
    $link = $workflow.links | Where-Object { [int]$_[0] -eq $id }
    $link[1] = $clipDisplayNodeId
    $link[2] = 0
}
$clipController = $workflow.nodes | Where-Object id -eq 2642
$clipController.outputs[0].links = $null

$project.outputs[3].links = @($projectTokenLink)
$project.outputs[4].links = @($projectClipLink)
$project.outputs[5].links = @($sourceVideoLink)
$project.outputs[6].links = @($contextPathLink)

$workflow.nodes = @($workflow.nodes) + $contextLoader
$workflow.nodes = @($workflow.nodes | Where-Object { [int]$_.id -ne 2642 })
$workflow.nodes = @($workflow.nodes) + $clipDisplay
$workflow.links = @($workflow.links) +
    ,@($contextPathLink, $nodeId, 6, $contextNodeId, 0, 'STRING') +
    ,@($projectTokenLink, $nodeId, 3, $contextNodeId, 1, 'STRING') +
    ,@($contextLatentLink, $contextNodeId, 0, 201, 9, 'LATENT') +
    ,@($sourceVideoLink, $nodeId, 5, 2616, 1, 'STRING') +
    ,@($projectClipLink, $nodeId, 4, $clipDisplayNodeId, 0, 'INT')

$workflow.last_node_id = $clipDisplayNodeId
$workflow.last_link_id = $linkId
$workflow.revision = [int]$workflow.revision + 1
$workflow.extra.h3_longform_seedhunter.release_version = '1.4-dev'
$workflow.extra.h3_longform_seedhunter | Add-Member -NotePropertyName project_state_schema -NotePropertyValue 2
$workflow.extra.pixaromaGroups = @($workflow.extra.pixaromaGroups) + [pscustomobject]@{
    id='pg_seedhunter_project_v14'; title='PROJECT STATE — CREATE / LOAD / RESUME'
    x=-3490; y=-750; w=680; h=340
    titleColor='#4f9497'; bodyColor='#173334'; titleAlpha=0.92; bodyAlpha=0.5
    fontSize=18; wOpen=680; hOpen=340; folded=$false; showLinks=$true
}

$workflow | ConvertTo-Json -Depth 100 -Compress | Set-Content -LiteralPath $target -Encoding utf8NoBOM
Write-Output $target
