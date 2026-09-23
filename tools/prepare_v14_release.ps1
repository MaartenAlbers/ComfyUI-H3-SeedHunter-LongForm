param(
    [string]$Workflow = (Join-Path (Split-Path $PSScriptRoot -Parent) 'Maartificial_H3_SeedHunter_Long_Form_Video_v1.4.json')
)

$ErrorActionPreference = 'Stop'
$data = Get-Content -LiteralPath $Workflow -Raw | ConvertFrom-Json

function Get-WorkflowNode([int]$Id) {
    $node = $data.nodes | Where-Object { $_.id -eq $Id }
    if (-not $node) { throw "Workflow node $Id was not found." }
    return $node
}

# Remove the active local project and make the project controller start neutral.
$project = Get-WorkflowNode 2690
$project.title = 'PROJECT — CREATE OR LOAD LONG-FORM STATE'
$project.widgets_values = @('my_first_project', 'load project', 'No project loaded', $null, $null, $null, $null, 'Start from beginning')
$project.widgets_values_named.project_name = 'my_first_project'
$project.widgets_values_named.action = 'load project'
$project.widgets_values_named.'PROJECT STATUS' = 'No project loaded'
$project.widgets_values_named.'CONTINUE FROM CLIP' = 'Start from beginning'
$project.properties.PSObject.Properties.Remove('seedhunter_project')
$project.properties.PSObject.Properties.Remove('seedhunter_project_names')
$project.properties.PSObject.Properties.Remove('seedhunter_clip_choice_map')

$clipIndex = Get-WorkflowNode 2692
$clipIndex.title = 'CURRENT PROJECT CLIP — 1 (MANIFEST CONTROLLED)'
$clipIndex.widgets_values = @('1')
$clipIndex.widgets_values_named.'CURRENT PROJECT CLIP' = '1'

$source = Get-WorkflowNode 2616
$source.widgets_values = @('new clip', '', $true, '')
$source.widgets_values_named.start_mode = 'new clip'
$source.widgets_values_named.video = ''
$source.widgets_values_named.use_source_audio = $true
$source.widgets_values_named.'PROJECT SOURCE PREVIEW' = ''

# Replace personal reference media and the test prompt with reusable placeholders.
foreach ($id in 2687, 2663, 2664, 2665) {
    $node = Get-WorkflowNode $id
    $node.widgets_values[0] = ''
    $node.widgets_values_named.image = ''
}

$starterPrompt = @'
integrated_multimodal_description:
  <Picture 1> is the primary visual reference. Describe the subject,
  environment, action, camera movement, lighting and continuity required
  for this clip. For an extension, continue the incoming pose, motion,
  expression and camera trajectory before introducing the new action.

overall_soundscape:
  Describe dialogue, ambience and other required sound. Explain the role
  of every enabled <Audio N> reference.

non_diegetic_music: N/A
'@
$promptNode = Get-WorkflowNode 200
$promptNode.widgets_values[0] = $starterPrompt.Trim()
$promptNode.widgets_values[3] = 243
$promptNode.widgets_values_named.prompt = $starterPrompt.Trim()
$promptNode.widgets_values_named.length = 243

# Clear rendered-media previews and local absolute output paths.
foreach ($node in $data.nodes) {
    if ($node.widgets_values_named) {
        $node.widgets_values_named.PSObject.Properties.Remove('videopreview')
    }
    if ($node.widgets_values -is [pscustomobject]) {
        $node.widgets_values.PSObject.Properties.Remove('videopreview')
    }
}

# Start the public workflow in three-preview scouting mode.
foreach ($node in $data.nodes) {
    $x = [double]$node.pos[0]
    $y = [double]$node.pos[1]

    # Preview candidate/output columns.
    if ($x -ge 670 -and $x -le 1900 -and $y -ge 680 -and $y -le 1810) {
        $node.mode = 0
    }

    # Hybrid final-pass section.
    if ($x -ge 1940 -and $x -le 3397 -and $y -ge -180 -and $y -le 1810) {
        $node.mode = 4
    }
}

foreach ($id in 2628, 2629, 2630) { (Get-WorkflowNode $id).mode = 4 }
(Get-WorkflowNode 2689).mode = 4

$previewControl = Get-WorkflowNode 2632
$previewControl.title = 'CHOOSE PREVIEW FOR FINAL PASS'
$previewControl.properties.seedhunter_final_pass_armed = $false
$previewControl.properties.seedhunter_preview_output_modes = [pscustomobject]@{
    '2296' = 0
    '2624' = 0
    '2626' = 0
}

$data.extra.h3_longform_seedhunter.release_version = '1.4'
$data.revision = [int]$data.revision + 1

$json = $data | ConvertTo-Json -Depth 100 -Compress
$temporaryWorkflow = "$Workflow.release-tmp"
[System.IO.File]::WriteAllText($temporaryWorkflow, $json, [System.Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temporaryWorkflow -Destination $Workflow -Force

Write-Host "Prepared public v1.4 workflow: $Workflow"
