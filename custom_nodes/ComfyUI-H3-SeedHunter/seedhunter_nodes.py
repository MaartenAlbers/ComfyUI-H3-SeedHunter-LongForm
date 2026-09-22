"""Audio modes and two-pass continuation for the SeedHunter 2.6 workflow."""

import os
import importlib

import torch
import comfy.nested_tensor
import folder_paths
import nodes
from comfy_extras.nodes_audio import load as load_audio, vae_decode_audio

from .project_state import accept_clip, create_project, project_snapshot, project_stamp

# Resolve the existing H3 package only during execution, after custom-node loading.
# Do not import its __init__ again or register/patch any of its node classes.
def _h3(module):
    anchor = nodes.NODE_CLASS_MAPPINGS.get("MiniMaxH3SongMaskedAVContext")
    if anchor is None:
        raise RuntimeError(
            "SeedHunter requires ComfyUI-H3-Motion-Context-MultiRef "
            "(tested revision 2ed4b27). Install it and restart ComfyUI.")
    package = anchor.__module__.rsplit(".", 1)[0]
    return importlib.import_module(f"{package}.{module}")


MODES = ["locked audio", "audio reference", "generate audio", "silent audio"]


def _path(value):
    value = value.strip().strip('"')
    return value if os.path.isabs(value) else folder_paths.get_annotated_filepath(value)


def _stamp(value):
    path = _path(value)
    if not os.path.isfile(path):
        return (path, None)
    info = os.stat(path)
    return (path, info.st_size, info.st_mtime_ns)


def _silence(frames, rate=32000):
    return {"waveform": torch.zeros(1, 2, round(frames / 24 * rate)), "sample_rate": rate}


class H3SeedHunterAudioInput:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "audio_mode": (MODES,),
            "audio_file": ("STRING", {"default": "", "tooltip": "Input-folder filename or absolute path. Ignored in generate audio mode."}),
        }}

    RETURN_TYPES = ("STRING", "AUDIO", "AUDIO")
    RETURN_NAMES = ("audio_mode", "master_audio", "reference_audio")
    FUNCTION = "load"
    CATEGORY = "conditioning/minimax/seedhunter"

    def load(self, audio_mode, audio_file=""):
        if audio_mode in ("generate audio", "silent audio"):
            return (audio_mode, None, None)
        if audio_mode not in MODES:
            raise ValueError("Unknown SeedHunter audio mode")
        if not audio_file.strip():
            raise ValueError("Choose an audio file, or select generate audio.")
        waveform, rate = load_audio(_path(audio_file))
        audio = {"waveform": waveform.unsqueeze(0), "sample_rate": rate}
        return (audio_mode, audio if audio_mode == "locked audio" else None,
                audio if audio_mode == "audio reference" else None)

    @classmethod
    def IS_CHANGED(cls, audio_mode, audio_file=""):
        return audio_mode if audio_mode == "generate audio" else _stamp(audio_file)


class H3SeedHunterAudioRouter:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"audio_mode": (MODES,)}, "optional": {
            name: ("AUDIO", {"lazy": True}) for name in
            ("master_audio", "reference_1", "reference_2", "reference_3")
        }}

    RETURN_TYPES = ("STRING", "AUDIO", "AUDIO", "AUDIO", "AUDIO")
    RETURN_NAMES = ("audio_mode", "master_audio", "reference_1", "reference_2", "reference_3")
    FUNCTION = "route"
    CATEGORY = "conditioning/minimax/seedhunter"

    def check_lazy_status(self, audio_mode, **kwargs):
        active = ("master_audio",) if audio_mode == "locked audio" else (
            ("reference_1", "reference_2", "reference_3") if audio_mode == "audio reference" else ())
        return [name for name in active if name in kwargs and kwargs[name] is None]

    def route(self, audio_mode, master_audio=None, reference_1=None, reference_2=None, reference_3=None):
        if audio_mode == "locked audio":
            if master_audio is None:
                raise ValueError("Connect and enable the master Load Audio node for locked audio.")
            return (audio_mode, master_audio, None, None, None)
        if audio_mode == "audio reference":
            if all(a is None for a in (reference_1, reference_2, reference_3)):
                raise ValueError("Connect and enable at least one reference Load Audio node.")
            return (audio_mode, None, reference_1, reference_2, reference_3)
        if audio_mode in ("generate audio", "silent audio"): 
            return (audio_mode, None, None, None, None)
        raise ValueError("Unknown SeedHunter audio mode")


class H3SeedHunterSourceVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "start_mode": (["new clip", "extend video"],),
            "video": ("STRING", {"default": ""}),
            "use_source_audio": ("BOOLEAN", {"default": True, "tooltip": "Disable for a silent source video. New audio will start in the extension."}),
        }}

    RETURN_TYPES = ("IMAGE", "AUDIO", "INT")
    RETURN_NAMES = ("source_frames", "source_audio", "frame_count")
    FUNCTION = "load"
    CATEGORY = "conditioning/minimax/seedhunter"

    def load(self, start_mode, video="", use_source_audio=True):
        if start_mode == "new clip":
            return (None, None, 0)
        path = _path(video)
        if not os.path.isfile(path):
            raise ValueError("Select an existing local source video, or select new clip.")
        # VHS owns decoding and path validation. Load the full source for assembly;
        # the context nodes themselves select the tail at each target resolution.
        frames, count, audio, _ = nodes.NODE_CLASS_MAPPINGS["VHS_LoadVideoPath"]().load_video(
            video=path, force_rate=24, custom_width=0, custom_height=0,
            frame_load_cap=0, skip_first_frames=0, select_every_nth=1, format="None")
        return (frames, dict(audio) if use_source_audio else _silence(count), count)

    @classmethod
    def IS_CHANGED(cls, start_mode, video="", use_source_audio=True):
        return start_mode if start_mode == "new clip" else (_stamp(video), use_source_audio)


class H3SeedHunterAVContext:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT",), "vae": ("VAE",), "audio_vae": ("VAE",),
            "audio_mode": ("STRING", {"forceInput": True}),
            "clip_start_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "step": 0.001}),
            "context_length": ("INT", {"default": 39, "min": 39, "step": 51}),
        }, "optional": {
            "master_audio": ("AUDIO",), "source_frames": ("IMAGE",),
            "source_audio": ("AUDIO",), "context_latent": ("LATENT",),
        }}

    RETURN_TYPES = ("LATENT", "INT", "AUDIO")
    RETURN_NAMES = ("latent", "overlap_frames", "locked_clip_audio")
    FUNCTION = "prepare"
    CATEGORY = "conditioning/minimax/seedhunter"

    def prepare(self, latent, vae, audio_vae, audio_mode, clip_start_seconds=0.0,
                context_length=39, master_audio=None, source_frames=None,
                source_audio=None, context_latent=None):
        n = 0
        if source_frames is not None:
            video, _ = _h3("existing_video_extension")._streams_from_latent(latent)
            n = _h3("existing_video_extension")._snap_context_length(context_length, len(source_frames), _h3("existing_video_extension")._pixel_frames(video.shape[2]))
        if audio_mode == "locked audio":
            if master_audio is None:
                raise ValueError("Locked audio needs a master audio file.")
            return _h3("h3_song_audio_context").MiniMaxH3SongMaskedAVContext().prepare(
                latent, audio_vae, master_audio, clip_start_seconds, n, 24.0,
                "disabled", vae=vae, source_frames=source_frames)
        if audio_mode not in MODES:
            raise ValueError("Unknown SeedHunter audio mode")
        if source_frames is None:
            out = latent.copy()
            out.pop("noise_mask", None)
            return (out, 0, None)
        if source_audio is None:
            source_audio = _silence(len(source_frames))
        out, overlap, _, _ = _h3("existing_video_extension").MiniMaxH3ExistingVideoMaskedContext().prepare(
            latent, vae, audio_vae, source_frames, source_audio, 24.0,
            n, "disabled", audio_feather_ticks=0)
        if context_latent is not None and audio_mode in ("audio reference", "generate audio"):
            # Keep the visual prefix encoded from the accepted MP4, but replace
            # the audio prefix with the previous sampler's original H3 latent.
            # This avoids a lossy MP4 decode -> audio VAE encode round trip.
            target_video, target_audio = _h3("existing_video_extension")._streams_from_latent(out)
            _, previous_audio = _h3("existing_video_extension")._streams_from_latent(context_latent)
            audio_steps = int(round(int(overlap) / 24.0 * 40.0))
            if audio_steps < 1 or audio_steps >= int(target_audio.shape[-1]):
                raise ValueError("Saved audio context does not fit the continuation target.")
            if int(previous_audio.shape[-1]) < audio_steps:
                raise ValueError("Saved context latent has too little audio for this overlap.")
            if tuple(previous_audio.shape[1:3]) != tuple(target_audio.shape[1:3]):
                raise ValueError(
                    "Saved and target H3 audio latent geometry do not match."
                )
            target_audio = target_audio.clone()
            target_audio[..., :audio_steps] = previous_audio[..., -audio_steps:].to(
                device=target_audio.device, dtype=target_audio.dtype
            )
            out["samples"] = comfy.nested_tensor.NestedTensor((target_video, target_audio))
        return (out, overlap, None)


class H3SeedHunterProjectContext:
    """Load the accepted project's previous H3 AV latent when one exists."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent_path": ("STRING", {"forceInput": True}),
            "project_token": ("STRING", {"forceInput": True}),
        }}

    RETURN_TYPES = ("LATENT",)
    RETURN_NAMES = ("context_latent",)
    FUNCTION = "load"
    CATEGORY = "conditioning/minimax/seedhunter/project"
    DESCRIPTION = (
        "Load the previous accepted clip's H3 AV safetensor. An empty path on "
        "clip 1 intentionally returns no context."
    )

    def load(self, latent_path, project_token):
        if not str(latent_path).strip():
            return (None,)
        return _h3("nodes").MiniMaxH3MotionContextLoadLatent().load(
            str(latent_path), 0
        )

    @classmethod
    def IS_CHANGED(cls, latent_path, project_token):
        if not str(latent_path).strip():
            return (str(project_token), "no-context")
        return (str(project_token), _stamp(str(latent_path)))


class H3SeedHunterProjectClipIndex:
    """Read-only manifest clip index relay with a browser-visible status card."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "clip_index": ("INT", {"forceInput": True}),
        }}

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("clip_index",)
    FUNCTION = "relay"
    CATEGORY = "conditioning/minimax/seedhunter/project"
    DESCRIPTION = (
        "Displays and relays the next clip index from Project State. The value "
        "is manifest-controlled and cannot be edited independently."
    )

    def relay(self, clip_index):
        return (int(clip_index),)


class H3SeedHunterRefineContext:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT",), "vae": ("VAE",),
            "overlap_frames": ("INT", {"forceInput": True}),
        }, "optional": {"source_frames": ("IMAGE",)}}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "prepare"
    CATEGORY = "conditioning/minimax/seedhunter"

    def prepare(self, latent, vae, overlap_frames, source_frames=None):
        _h3("existing_video_extension")._require_h3_mask_support()
        video, audio = _h3("existing_video_extension")._streams_from_latent(latent)
        video = video.clone()
        vm = torch.ones((1, 1, *video.shape[2:]), device=video.device, dtype=torch.float32)
        am = torch.zeros((1, 1, *audio.shape[2:]), device=audio.device, dtype=torch.float32)
        n = int(overlap_frames)
        if n:
            if source_frames is None or len(source_frames) < n:
                raise ValueError("Final pass needs the same source frames used by the previews.")
            frames = _h3("existing_video_extension")._resize_images(source_frames[-n:], video.shape[4] * 16, video.shape[3] * 16, "disabled")
            prefix = vae.encode(frames)
            steps = prefix.shape[2]
            if _h3("existing_video_extension")._pixel_frames(steps) != n or steps >= video.shape[2]:
                raise ValueError("Final-pass overlap does not fit the H3 temporal grid.")
            video[:, :, :steps] = prefix.to(device=video.device, dtype=video.dtype)
            vm[:, :, :steps] = 0
        out = latent.copy()
        out["samples"] = comfy.nested_tensor.NestedTensor((video, audio))
        out["noise_mask"] = comfy.nested_tensor.NestedTensor((vm, am))
        return (out,)


class H3SeedHunterOutputAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT",), "audio_vae": ("VAE",),
            "audio_mode": ("STRING", {"forceInput": True}),
        }, "optional": {"locked_clip_audio": ("AUDIO",)}}

    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "decode"
    CATEGORY = "conditioning/minimax/seedhunter"

    def decode(self, latent, audio_vae, audio_mode, locked_clip_audio=None):
        video, _ = _h3("existing_video_extension")._streams_from_latent(latent)
        if audio_mode == "silent audio":
            return (_silence(_h3("existing_video_extension")._pixel_frames(video.shape[2])),)
        if audio_mode == "locked audio":
            if locked_clip_audio is None:
                raise ValueError("Locked clip audio is missing.")
            return (locked_clip_audio,)
        audio = vae_decode_audio(audio_vae, latent)
        return (_h3("existing_video_extension")._canonical_audio(audio, audio["sample_rate"], _h3("existing_video_extension")._pixel_frames(video.shape[2])),)


class H3SeedHunterAssemble:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",), "audio": ("AUDIO",),
            "overlap_frames": ("INT", {"forceInput": True}),
        }, "optional": {"source_frames": ("IMAGE",), "source_audio": ("AUDIO",)}}

    RETURN_TYPES = ("IMAGE", "AUDIO")
    FUNCTION = "assemble"
    CATEGORY = "conditioning/minimax/seedhunter"

    def assemble(self, images, audio, overlap_frames, source_frames=None, source_audio=None):
        sr = int(audio["sample_rate"])
        audio = _h3("existing_video_extension")._canonical_audio(audio, sr, len(images))
        if source_frames is None:
            return (images, audio)
        n = int(overlap_frames)
        if n < 1 or n >= len(images) or n > len(source_frames):
            raise ValueError("Assembly overlap must match the context used for sampling.")
        source = _h3("existing_video_extension")._resize_images(source_frames, images.shape[2], images.shape[1], "disabled")
        if source_audio is None:
            source_audio = _silence(len(source), sr)
        source_audio = _h3("existing_video_extension")._canonical_audio(source_audio, sr, len(source))
        weight = torch.linspace(0, 1, n, device=images.device, dtype=images.dtype).reshape(n, 1, 1, 1)
        seam = source[-n:].to(images.device) * (1 - weight) + images[:n] * weight
        result = torch.cat((source[:-n].to(images.device), seam, images[n:]), dim=0)
        cut = round((len(source) - n) / 24 * sr)
        # Difference of rounded boundaries keeps accumulated duration exact.
        overlap_samples = round(len(source) / 24 * sr) - cut
        wave = audio["waveform"]
        previous = source_audio["waveform"].to(device=wave.device, dtype=wave.dtype)
        weight_a = torch.linspace(0, 1, overlap_samples, device=wave.device, dtype=wave.dtype)
        seam_a = previous[..., cut:] * (1 - weight_a) + wave[..., :overlap_samples] * weight_a
        joined = torch.cat((previous[..., :cut], seam_a, wave[..., overlap_samples:]), dim=-1)
        output = _h3("existing_video_extension")._canonical_audio({"waveform": joined, "sample_rate": sr}, sr, len(result))
        return (result, output)


class H3SeedHunterSinglePassControl:
    """UI preset controller; its browser extension switches the workflow routes."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "preview_megapixels": ("FLOAT", {"default": 0.5, "min": 0.1, "max": 4.0, "step": 0.05}),
            "single_pass_megapixels": ("FLOAT", {"default": 1.5, "min": 0.1, "max": 4.0, "step": 0.05}),
            "aspect_ratio": ([
                "16:9 (Widescreen)", "9:16 (Portrait Widescreen)",
                "1:1 (Square)", "2:3 (Portrait Photo)", "3:2 (Photo)",
                "3:4 (Portrait Standard)", "4:3 (Standard)",
                "21:9 (Ultrawide)",
            ],),
            "final_pass_megapixels": ("FLOAT", {"default": 1.5, "min": 0.1, "max": 4.0, "step": 0.05}),
        }}

    RETURN_TYPES = ("FLOAT", "FLOAT", "STRING", "FLOAT")
    RETURN_NAMES = (
        "preview_megapixels", "single_pass_megapixels", "aspect_ratio",
        "final_pass_megapixels",
    )
    FUNCTION = "values"
    CATEGORY = "conditioning/minimax/seedhunter"

    def values(self, preview_megapixels, single_pass_megapixels, aspect_ratio,
               final_pass_megapixels):
        return (
            float(preview_megapixels), float(single_pass_megapixels),
            str(aspect_ratio), float(final_pass_megapixels),
        )


class H3SeedHunterProject:
    """Create or load a persistent SeedHunter long-form project."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "project_name": ("STRING", {
                "default": "my_first_project",
                "multiline": False,
                "tooltip": "Folder name under ComfyUI/output/h3_projects.",
            }),
            "action": (["load project", "create project"],),
        }}

    RETURN_TYPES = ("STRING", "STRING", "INT", "STRING", "INT", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "project_path", "project_id", "project_revision", "project_token",
        "next_clip_index", "previous_clip_video", "previous_context_latent",
        "master_audio", "project_status",
    )
    FUNCTION = "open"
    CATEGORY = "conditioning/minimax/seedhunter/project"
    DESCRIPTION = (
        "Create or load an H3 long-form project manifest. The project token "
        "changes with every manifest revision so downstream cache keys cannot "
        "silently reuse another project's state."
    )

    def open(self, project_name, action):
        output = folder_paths.get_output_directory()
        if action == "create project":
            create_project(output, project_name)
        elif action != "load project":
            raise ValueError(f"Unknown project action: {action}")
        snapshot = project_snapshot(output, project_name)
        return tuple(snapshot[name] for name in (
            "project_path", "project_id", "revision", "project_token",
            "next_clip_index", "previous_clip_video", "previous_context_latent",
            "master_audio", "status",
        ))

    @classmethod
    def IS_CHANGED(cls, project_name, action):
        if action == "create project":
            return float("NaN")
        return (action, project_stamp(folder_paths.get_output_directory(), project_name))


class H3SeedHunterAcceptClip:
    """Commit an MP4/context pair to the currently loaded project revision."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "project_name": ("STRING", {"default": "my_first_project"}),
            "project_token": ("STRING", {"forceInput": True}),
            "clip_index": ("INT", {"forceInput": True}),
            "video_path": ("STRING", {"default": ""}),
            "context_path": ("STRING", {"default": ""}),
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "frame_count": ("INT", {"default": 243, "min": 1}),
            "overlap_frames": ("INT", {"default": 0, "min": 0}),
            "audio_mode": (MODES,),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "step": 0.001}),
        }}

    RETURN_TYPES = ("STRING", "INT", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "project_token", "next_clip_index", "accepted_video",
        "accepted_context", "project_status",
    )
    FUNCTION = "accept"
    OUTPUT_NODE = True
    CATEGORY = "conditioning/minimax/seedhunter/project"
    DESCRIPTION = (
        "Atomically register the next accepted final clip. The MP4 and matching "
        "H3 AV safetensor are copied into fixed project slots before project.json "
        "advances to the next clip."
    )

    def accept(self, project_name, project_token, clip_index, video_path,
               context_path, prompt, frame_count, overlap_frames, audio_mode,
               fps=24.0):
        snapshot = accept_clip(
            folder_paths.get_output_directory(), project_name, project_token,
            clip_index, video_path, context_path, prompt, frame_count,
            overlap_frames, audio_mode, fps,
        )
        return (
            snapshot["project_token"], snapshot["next_clip_index"],
            snapshot["previous_clip_video"],
            snapshot["previous_context_latent"], snapshot["status"],
        )


NODE_CLASS_MAPPINGS = {cls.__name__: cls for cls in (
    H3SeedHunterAudioInput, H3SeedHunterAudioRouter, H3SeedHunterSourceVideo, H3SeedHunterAVContext,
    H3SeedHunterRefineContext, H3SeedHunterOutputAudio, H3SeedHunterAssemble,
    H3SeedHunterSinglePassControl, H3SeedHunterProject, H3SeedHunterAcceptClip,
    H3SeedHunterProjectContext, H3SeedHunterProjectClipIndex,
)}
NODE_DISPLAY_NAME_MAPPINGS = {
    "H3SeedHunterAudioInput": "H3 SeedHunter Audio Mode",
    "H3SeedHunterAudioRouter": "H3 SeedHunter Audio Mode — External Loaders",
    "H3SeedHunterSourceVideo": "H3 SeedHunter New Clip / Extend Video",
    "H3SeedHunterAVContext": "H3 SeedHunter Preview AV Context",
    "H3SeedHunterRefineContext": "H3 SeedHunter Final Context + Keep Selected Audio",
    "H3SeedHunterOutputAudio": "H3 SeedHunter Output Audio",
    "H3SeedHunterAssemble": "H3 SeedHunter Seamless Assembly",
    "H3SeedHunterSinglePassControl": "H3 SeedHunter Single Pass Control",
    "H3SeedHunterProject": "H3 SeedHunter Long-Form Project",
    "H3SeedHunterAcceptClip": "H3 SeedHunter Accept Clip Into Project",
    "H3SeedHunterProjectContext": "H3 SeedHunter Load Project Context",
    "H3SeedHunterProjectClipIndex": "H3 SeedHunter Current Project Clip",
}
