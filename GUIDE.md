# H3 SeedHunter Long-Form Video

This workflow combines fast SeedHunter previews, a selected high-resolution refinement pass, and seamless audiovisual continuation. It supports three audio modes:

- **Locked audio:** use an existing soundtrack as the exact audio timeline.
- **Audio reference:** guide MiniMax with one or more reference recordings while it generates new audio.
- **Generate audio:** let MiniMax generate the audio described in the prompt.

## 1. Install the requirements

Install the required models and custom-node packages listed in the workflow's **DOWNLOAD LINKS + CREDITS** note.

The workflow also requires the two included helper packages:

- `ComfyUI-H3-SeedHunter`
- `ComfyUI-H3-SeedHunter-FFmpeg`

Place both folders in `ComfyUI/custom_nodes/`, then restart ComfyUI. Load the workflow and replace every placeholder image, audio file and optional source video.

## 2. Choose how to start

Find **START — new clip / seamless extension (FFmpeg)**.

- **new clip:** starts a new sequence. The source-video field is ignored.
- **extend video:** continues from the selected source video.

For the first clip, choose **new clip** and keep **NEXT CLIP NUMBER** at `1`.

Only increment the clip number after accepting a finished result. In locked-audio mode, this number determines the correct soundtrack position automatically.

## 3. Choose the audio mode

Find **AUDIO MODE — external Load Audio inputs**.

### Locked audio

Choose **locked audio** and load the complete soundtrack in **MASTER — exact locked soundtrack**.

The workflow automatically extracts the correct song section from the master track using the clip number, actual H3 frame count and protected overlap. The audio remains protected during preview generation and final refinement.

### Audio reference

Choose **audio reference** and load a recording in **REFERENCE 1 — `<Audio 1>`**. References 2 and 3 are optional and bypassed by default; enable them with `Ctrl+B` only when needed.

Explain the purpose of each enabled audio reference in the prompt. An audio reference can define qualities such as voice, accent, delivery or sound style. Its duration does not determine the generated video duration.

### Generate audio

Choose **generate audio**. No external audio is required. Describe the dialogue, performance, ambience and other desired sound directly in the prompt.

## 4. Set the clip duration

Use **Number of seconds clip** to set the requested raw generation length.

MiniMax H3 uses a `17k+5` frame grid, so the workflow snaps the request upward to a valid frame count. At the default 24 fps and 10-second request:

| Operation | Result |
|---|---:|
| Raw H3 clip | 243 frames / 10.125 seconds |
| Protected overlap | 39 frames / 1.625 seconds |
| New timeline contribution | 204 frames / 8.5 seconds |

The overlap is part of the generated continuation. The seamless assembler removes the duplicate duration; it is never added twice.

The overlap node can select a larger H3-safe value when the requested context and available source frames allow it. The default is 39 frames.

## 5. Add references and write the prompt

Load your reference images and edit **ROLLING CLIP — MiniMax H3 Reference to Video**.

Make sure every `<Picture N>`, `<Audio N>` and `<Video 1>` reference mentioned in the prompt matches an enabled, connected input. Describe:

- stable subject identity and wardrobe;
- environment and visual style;
- physical action and camera movement;
- the purpose of every reference;
- exact dialogue or lyrics when applicable;
- the motion that should continue into the next clip.

For an extension, begin by continuing the incoming pose, expression, camera trajectory, lighting and physical momentum. Do not treat the generation boundary as a new shot unless an actual cut is intended.

## 6. Generate preview candidates

Keep **HYBRID FINAL UPSCALE PASS** disabled while scouting.

Enable the preview candidates you want and click **Run**. The default preview resolution is **0.5 MP**. Each candidate uses a different seed but shares the same prompt, references, timing and audio mode.

Review both picture and sound. The fast latent preview is only a progress aid; judge timing, duration and synchronization from the saved preview video.

## 7. Select one preview

Enable exactly one group:

- **SELECT PREVIEW 1**
- **SELECT PREVIEW 2**
- **SELECT PREVIEW 3**

Bypass the other two selection groups. Only a completed preview can be refined.

Do not change the prompt, references, duration, model settings or selected preview seed between the preview run and final run. Keeping the upstream inputs unchanged lets ComfyUI reuse cached preview results. Restarting ComfyUI clears that in-memory cache.

## 8. Run the final pass

Enable **HYBRID FINAL UPSCALE PASS**, then run the workflow again.

The selected preview latent is upscaled and refined at the configured final resolution, which defaults to **1.5 MP**. The selected audio remains protected. In extension mode, the incoming visual overlap is restored and protected at the final resolution.

The output **FINAL SELECTED CLIP — 1.5 MP** contains the newly rendered raw clip, including its incoming overlap when this is an extension.

## 9. Assemble and continue

For a first clip, the final selected clip can be used directly.

For an extension, enable **FULL SEAMLESS VIDEO — load this to extend again**. This output:

1. keeps the existing source sequence;
2. blends the protected overlap once;
3. appends only the genuinely new frames and matching audio.

Use the newest **FULL SEAMLESS VIDEO** as the source for the next extension. Set **START** to **extend video**, increment **NEXT CLIP NUMBER** by one, update the prompt, disable the final pass, and scout new previews.

If the source file has no usable audio, disable `use_source_audio`. The workflow supplies correctly timed silence for the existing section so newly generated audio stays aligned.

## 10. Write for the overlap

With the default 39-frame overlap, the first 1.625 seconds of an extension are protected incoming context.

Continue the existing motion through this section. Avoid placing a new line of dialogue, a major action, a cut or a visual reset entirely inside the protected prefix. Introduce the new development after the overlap while preserving momentum across the seam.

## 11. Review before advancing

Before accepting a continuation, inspect:

- identity, wardrobe and environment continuity;
- camera direction and speed;
- body and object momentum;
- lip-sync or dialogue timing;
- audio continuity and absence of duplicated overlap;
- the beginning and end of the blended seam.

Advance the clip number only after accepting the result. Keep a copy of the workflow together with the matching helper-node versions so the sequence can be reproduced later.

## Credits

- SeedHunter foundation: [Fox•Fur•Essence Films](https://www.youtube.com/@foxfuressence)
- Long-form protected motion-context foundation: [Seitanism — ComfyUI-H3-Motion-Context-MultiRef](https://github.com/seitanism/ComfyUI-H3-Motion-Context-MultiRef)

