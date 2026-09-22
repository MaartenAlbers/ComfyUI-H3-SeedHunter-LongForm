$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root 'H3_SeedHunter_Long_Form_Video_v1.3.1.json'
$target = Join-Path $root 'H3_SeedHunter_Long_Form_Video_v1.4_DEV.json'
$workflow = Get-Content -LiteralPath $source -Raw | ConvertFrom-Json

if ($workflow.nodes | Where-Object type -eq 'H3SeedHunterProject') {
    throw 'The source workflow already contains an H3SeedHunterProject node.'
}

$nodeId = [int]$workflow.last_node_id + 1
$order = (($workflow.nodes | Measure-Object -Property order -Maximum).Maximum + 1)
$project = [pscustomobject]@{
    id = $nodeId
    type = 'H3SeedHunterProject'
    pos = @(-3460.0, -700.0)
    size = @(620.0, 220.0)
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
$workflow.last_node_id = $nodeId
$workflow.revision = [int]$workflow.revision + 1
$workflow.extra.h3_longform_seedhunter.release_version = '1.4-dev'
$workflow.extra.h3_longform_seedhunter | Add-Member -NotePropertyName project_state_schema -NotePropertyValue 1
$workflow.extra.pixaromaGroups = @($workflow.extra.pixaromaGroups) + [pscustomobject]@{
    id='pg_seedhunter_project_v14'; title='PROJECT STATE — CREATE / LOAD / RESUME'
    x=-3490; y=-750; w=680; h=300
    titleColor='#4f9497'; bodyColor='#173334'; titleAlpha=0.92; bodyAlpha=0.5
    fontSize=18; wOpen=680; hOpen=300; folded=$false; showLinks=$true
}

$workflow | ConvertTo-Json -Depth 100 -Compress | Set-Content -LiteralPath $target -Encoding utf8NoBOM
Write-Output $target
