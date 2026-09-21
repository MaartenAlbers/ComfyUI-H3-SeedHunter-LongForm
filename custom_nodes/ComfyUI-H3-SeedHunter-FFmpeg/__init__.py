"""Separate FFmpeg source loader; leaves the original SeedHunter nodes unchanged."""

import importlib
import os

import nodes


def _original_module():
    return importlib.import_module(nodes.NODE_CLASS_MAPPINGS["H3SeedHunterSourceVideo"].__module__)


class H3SeedHunterSourceVideoFFmpeg:
    @classmethod
    def INPUT_TYPES(cls):
        return nodes.NODE_CLASS_MAPPINGS["H3SeedHunterSourceVideo"].INPUT_TYPES()

    RETURN_TYPES = ("IMAGE", "AUDIO", "INT")
    RETURN_NAMES = ("source_frames", "source_audio", "frame_count")
    FUNCTION = "load"
    CATEGORY = "conditioning/minimax/seedhunter"

    def load(self, start_mode, video="", use_source_audio=True):
        if start_mode == "new clip":
            return (None, None, 0)
        original = _original_module()
        path = original._path(video)
        if not os.path.isfile(path):
            raise ValueError("Select an existing local source video, or select new clip.")
        frames, _, audio, _ = nodes.NODE_CLASS_MAPPINGS["VHS_LoadVideoFFmpegPath"]().load_video(
            video=path, force_rate=24, custom_width=0, custom_height=0,
            frame_load_cap=0, start_time=0, format="None")
        count = len(frames)
        return (frames, dict(audio) if use_source_audio else original._silence(count), count)

    @classmethod
    def IS_CHANGED(cls, start_mode, video="", use_source_audio=True):
        return nodes.NODE_CLASS_MAPPINGS["H3SeedHunterSourceVideo"].IS_CHANGED(
            start_mode, video, use_source_audio)


NODE_CLASS_MAPPINGS = {"H3SeedHunterSourceVideoFFmpeg": H3SeedHunterSourceVideoFFmpeg}
NODE_DISPLAY_NAME_MAPPINGS = {
    "H3SeedHunterSourceVideoFFmpeg": "H3 SeedHunter New Clip / Extend Video (FFmpeg)"
}
