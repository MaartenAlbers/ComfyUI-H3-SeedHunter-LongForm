# Changelog

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
