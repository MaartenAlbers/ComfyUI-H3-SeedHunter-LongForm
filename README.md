# H3 SeedHunter — Long-Form Video

An experimental ComfyUI workflow for generating several MiniMax H3 preview candidates, selecting one result, refining it at higher resolution and extending accepted clips into a seamless audiovisual sequence.

## Download

Download the latest release package from the repository's **Releases** page. The workflow file is:

`H3_SeedHunter_Long_Form_Video_v1.3.1.json`

Models and example media are not included.

## Main features

- Three fast SeedHunter preview candidates.
- One selected 1.5 MP refinement pass.
- Configurable one-click single-pass mode.
- Automatic motion/audio-context checkpoint saving for Single Pass Mode, so Locked Audio can continue into the next clip.
- Seamless audiovisual continuation with protected overlap.
- Locked soundtrack, audio-reference and generated-audio modes.
- Optional low-VRAM and sparse-attention controls.

## Installation

1. Copy both folders from `custom_nodes/` into `ComfyUI/custom_nodes/`.
2. Install the external custom-node dependencies below, preferably with ComfyUI Manager.
3. Download the required MiniMax H3 models.
4. Restart ComfyUI.
5. Load `H3_SeedHunter_Long_Form_Video_v1.3.1.json`.
6. Replace the empty image, audio and optional source-video inputs before running.
7. Read [GUIDE.md](GUIDE.md), especially the preview-selection and extension sections.

## External custom-node dependencies

- [ComfyUI-H3-Motion-Context-MultiRef](https://github.com/seitanism/ComfyUI-H3-Motion-Context-MultiRef)
- [Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler)
- VideoHelperSuite
- KJNodes
- rgthree-comfy
- ComfyUI-Impact-Pack
- ComfyUI-Easy-Use
- WhatDreamsCost
- comfy-mtb

The workflow metadata records the custom-node versions used when it was saved. Exact compatibility can depend on the installed ComfyUI, node and model versions.

## Models

- [Comfy-Org MiniMax H3](https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main)
- [LightX2V MiniMax H3 Turbo](https://huggingface.co/lightx2v/Minimax-h3-Turbo)

The workflow currently expects these filenames:

- `diffusion_models/minimax/minimax_h3_ref2va_pruned_int8_convrot.safetensors`
- `text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- `vae/Minimax/minimax_h3_video_vae_int8_convrot.safetensors`
- `vae/Minimax/minimax_h3_audio_vae_fp32.safetensors`
- `loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors`
- `vae/taeh3.safetensors` for the live preview

If your folder layout differs, select the installed file in the corresponding loader node.

## Updating

The source workflow may contain local paths and project media. Create a clean public copy with:

```powershell
.\tools\New-PublicWorkflow.ps1 `
  -Source .\work\H3_SeedHunter_Long_Form_Video_NEXT.json `
  -Destination .\H3_SeedHunter_Long_Form_Video_vNEXT_PUBLIC.json
```

Inspect the result, update `CHANGELOG.md`, test it in a clean ComfyUI session and publish it as a new tagged release.

## Credits

- Workflow development and testing: [Fox•Fur•Essence](https://www.youtube.com/@foxfuressence)
- Motion-context foundation: [Seitanism / ComfyUI-H3-Motion-Context-MultiRef](https://github.com/seitanism/ComfyUI-H3-Motion-Context-MultiRef)

## License

The original workflow, documentation and helper code in this release are
dedicated to the public domain under [CC0 1.0 Universal](LICENSE). You may copy,
modify, redistribute and use them commercially without attribution.

External models, custom nodes and other dependencies retain their own licenses.
CC0 applies only to material the publisher is legally entitled to license.

## Status

This is an experimental release. Keep a copy of a working ComfyUI installation and record the exact model and custom-node versions used for successful renders.
