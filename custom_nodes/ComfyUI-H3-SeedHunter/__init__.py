"""Independent H3 SeedHunter nodes; no registration of existing H3 classes."""
import os
import shutil
from pathlib import Path

from aiohttp import web
import folder_paths
from server import PromptServer

from .seedhunter_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS


@PromptServer.instance.routes.post("/seedhunter/latest_output")
async def latest_output(request):
    """Find the newest saved video for a VHS filename prefix after UI reload."""
    data = await request.json()
    prefix = str(data.get("filename_prefix", "")).replace("\\", "/").strip("/")
    if not prefix:
        return web.json_response({"error": "Missing filename prefix."}, status=400)
    relative_dir, stem = os.path.split(prefix)
    roots = [Path(folder_paths.get_output_directory())]
    matches = []
    for root in roots:
        directory = root.joinpath(*relative_dir.split("/")) if relative_dir else root
        if directory.is_dir():
            matches.extend(path for path in directory.glob(f"{stem}*.mp4") if path.is_file())
    if not matches:
        return web.json_response({"error": f"No saved video found for {prefix}."}, status=404)
    newest = max(matches, key=lambda path: path.stat().st_mtime)
    return web.json_response({
        "path": str(newest),
        "filename": newest.name,
        "subfolder": relative_dir,
        "type": "output",
    })


@PromptServer.instance.routes.post("/seedhunter/copy_output_to_input")
async def copy_output_to_input(request):
    """Copy a rendered VHS output into ComfyUI input for LoadAudioUI."""
    data = await request.json()
    filename = os.path.basename(str(data.get("filename", "")))
    subfolder = str(data.get("subfolder", "")).replace("\\", "/").strip("/")
    fullpath = str(data.get("fullpath", "")).strip().strip('"')
    if not filename:
        return web.json_response({"error": "Missing output filename."}, status=400)

    if fullpath and os.path.basename(fullpath) == filename:
        source = os.path.abspath(fullpath)
    else:
        relative_output = f"{subfolder}/{filename}" if subfolder else filename
        try:
            source = folder_paths.get_annotated_filepath(f"{relative_output} [output]")
        except Exception as exc:
            return web.json_response({"error": f"Could not resolve output: {exc}"}, status=400)
    if not source or not os.path.isfile(source):
        return web.json_response({"error": "The rendered output file no longer exists."}, status=404)

    relative_input = f"seedhunter_references/{filename}"
    destination = os.path.join(folder_paths.get_input_directory(), *relative_input.split("/"))
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy2(source, destination)
    return web.json_response({"filename": relative_input})

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
