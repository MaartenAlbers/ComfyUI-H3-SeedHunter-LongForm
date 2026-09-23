# Changelog

## 1.4.0 — 2026-09-23

- Added persistent project creation, loading, switching and project-specific workflow state.
- Added accepted-clip history, active-timeline tracking and non-destructive rollback/branching.
- Added manifest-controlled continuation sources, clip numbers and saved audiovisual context.
- Added automatic restoration of prompts, reference images, format, run mode and final-pass controls.
- Separated aspect ratio from preview, Single Pass and final-pass resolution settings.
- Added active-timeline assembly with Delivery MP4 and ProRes 422 HQ master exports.
- Added optional rgthree Power LoRA Loader integration.
- Added in-workflow project, render-control and continuation documentation.
- Removed personal project state, media paths, test prompts and stale output previews from the public workflow.

## 1.3.1 — 2026-09-21

- Added a dedicated Preview 1 motion/audio-context checkpoint save for Single Pass Mode.
- Made **TURN ON SINGLE PASS** enable that save automatically, preserving the `.safetensors` context required by Locked Audio continuations.
- Made **RESTORE PREVIEW MODE** bypass the dedicated save again, preventing ordinary preview rerolls from writing checkpoints.
- Added **USE AS SOURCE FOR NEXT CLIP** to the Preview 1 video output while Single Pass Mode is active.

## 1.3.0 — 2026-09-21

- Added a configurable single-pass mode with separate preview and single-pass megapixel settings.
- Added one-click controls to enable single-pass mode and restore the previous preview/final-pass routing.
- Kept Preview 1 as the active single-pass generator and output while bypassing Preview 2, Preview 3, preview selection, hybrid refinement and full-sequence assembly.
- Fixed the public workflow's reference-image wiring so Picture 1–4 map correctly to H3 reference inputs 0–3.

## 1.2.0 — 2026-09-21

- Added the fourth reference-image input.
- Updated the saved workflow to the current ComfyUI frontend format.
- Removed local source paths, media filenames and stale output previews from the public build.
- Replaced the project-specific generation prompt with a reusable starter template.
- Released the original workflow, documentation and helper code under CC0 1.0 Universal.
