param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$Destination
)

$ErrorActionPreference = "Stop"

$workflow = Get-Content -LiteralPath $Source -Raw | ConvertFrom-Json -Depth 100

$starterPrompt = @"
subject_definitions:
  <Picture 1> is the primary visual reference. Describe exactly which
  identity, wardrobe, objects, environment or composition it controls.

summary:
  Describe the complete clip in one or two sentences.

retention_analysis:
  For an extension, preserve the incoming subject identity, wardrobe,
  environment, lighting, camera trajectory and physical momentum.
  State which details must remain unchanged throughout the clip.

detailed_description:
  Continue naturally from the incoming motion context when extending a
  video. Describe the action chronologically, including subject motion,
  camera movement, timing and the intended final state. Do not introduce
  a cut or reset inside the protected overlap unless an actual cut is
  intended.

overall_soundscape:
  Describe dialogue, performance, ambience and sound effects. When using
  locked audio, describe only visual synchronization and do not request
  replacement music or dialogue.

non_diegetic_music: N/A
"@

foreach ($node in $workflow.nodes) {
    switch ($node.type) {
        "LoadImage" {
            $node.widgets_values = @("", "image")
            if ($node.widgets_values_named) {
                $node.widgets_values_named.image = ""
            }
        }
        "LoadAudioUI" {
            $node.widgets_values = @("", 0, 0, 0, $null, "")
            if ($node.widgets_values_named) {
                $node.widgets_values_named.audio = ""
                $node.widgets_values_named.start_time = 0
                $node.widgets_values_named.end_time = 0
                $node.widgets_values_named.duration = 0
                $node.widgets_values_named.upload = $null
                if ($node.widgets_values_named.PSObject.Properties.Name -contains "audio_ui") {
                    $node.widgets_values_named.audio_ui = ""
                }
            }
        }
        "H3SeedHunterSourceVideoFFmpeg" {
            $node.widgets_values = @("new clip", "", $true)
            if ($node.widgets_values_named) {
                $node.widgets_values_named.start_mode = "new clip"
                $node.widgets_values_named.video = ""
                $node.widgets_values_named.use_source_audio = $true
            }
        }
        "MiniMaxH3ReferenceToVideo" {
            $node.widgets_values[0] = $starterPrompt.Trim()
            if ($node.widgets_values_named) {
                $node.widgets_values_named.prompt = $starterPrompt.Trim()
            }
        }
        "VHS_VideoCombine" {
            if ($node.widgets_values -and $node.widgets_values.PSObject.Properties.Name -contains "videopreview") {
                $node.widgets_values.videopreview = $null
            }
            if ($node.widgets_values_named -and $node.widgets_values_named.PSObject.Properties.Name -contains "videopreview") {
                $node.widgets_values_named.videopreview = $null
            }
        }
    }
}

if ($workflow.extra.PSObject.Properties.Name -contains "anomalous_hashes") {
    $workflow.extra.PSObject.Properties.Remove("anomalous_hashes")
}

if ($workflow.extra.h3_longform_seedhunter) {
    $workflow.extra.h3_longform_seedhunter.PSObject.Properties.Remove("source_longform")
    $workflow.extra.h3_longform_seedhunter.PSObject.Properties.Remove("source_seedhunter")
    $workflow.extra.h3_longform_seedhunter.PSObject.Properties.Remove("prototype_clip")
    $workflow.extra.h3_longform_seedhunter | Add-Member -NotePropertyName release_version -NotePropertyValue "1.2" -Force
}

$parent = Split-Path -Parent $Destination
if ($parent) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

$json = $workflow | ConvertTo-Json -Depth 100 -Compress
[System.IO.File]::WriteAllText($Destination, $json, [System.Text.UTF8Encoding]::new($false))

Write-Output "Created public workflow: $Destination"
