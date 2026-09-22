"""Persistent project manifests for H3 SeedHunter long-form productions."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
PROJECTS_FOLDER = "h3_projects"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_project_name(value):
    name = str(value).strip()
    if not name:
        raise ValueError("Project name cannot be empty.")
    if not _SAFE_NAME.fullmatch(name) or name in (".", ".."):
        raise ValueError(
            "Project name must start with a letter or number and contain only "
            "letters, numbers, spaces, dots, underscores, or hyphens (max 80)."
        )
    return name


def project_directory(output_directory, project_name):
    name = validate_project_name(project_name)
    root = Path(output_directory).resolve() / PROJECTS_FOLDER
    path = (root / name).resolve()
    if path.parent != root:
        raise ValueError("Project path escaped the H3 projects folder.")
    return path


def manifest_path(output_directory, project_name):
    return project_directory(output_directory, project_name) / "project.json"


def _write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=".project-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def create_project(output_directory, project_name):
    directory = project_directory(output_directory, project_name)
    path = directory / "project.json"
    if path.exists():
        raise FileExistsError(
            f"Project '{project_name}' already exists. Choose Load Project instead."
        )

    for child in (
        "media/references",
        "clips",
        "context",
        "prompts",
        "previews",
        "rejects",
        "renders",
    ):
        (directory / child).mkdir(parents=True, exist_ok=True)

    timestamp = _now()
    data = {
        "schema_version": SCHEMA_VERSION,
        "project_id": str(uuid.uuid4()),
        "name": validate_project_name(project_name),
        "created_at": timestamp,
        "updated_at": timestamp,
        "revision": 1,
        "workflow_version": "1.4-dev",
        "settings": {
            "audio_mode": "locked audio",
            "master_audio": "",
            "fps": 24.0,
            "context_frames": 39,
        },
        "next_clip_index": 1,
        "accepted_clips": [],
        "final_render": "",
    }
    _write_json_atomic(path, data)
    return data, directory


def load_project(output_directory, project_name):
    directory = project_directory(output_directory, project_name)
    path = directory / "project.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"Project '{project_name}' does not exist. Create it first."
        )
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    validate_manifest(data, directory)
    return data, directory


def validate_manifest(data, directory):
    if not isinstance(data, dict):
        raise ValueError("project.json must contain a JSON object.")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schema {data.get('schema_version')!r}; "
            f"this build supports schema {SCHEMA_VERSION}."
        )
    if not data.get("project_id"):
        raise ValueError("project.json has no project_id.")
    validate_project_name(data.get("name", ""))
    clips = data.get("accepted_clips")
    if not isinstance(clips, list):
        raise ValueError("project.json accepted_clips must be a list.")
    expected = 1
    for clip in clips:
        if not isinstance(clip, dict) or int(clip.get("index", -1)) != expected:
            raise ValueError("Accepted clips must be numbered consecutively from 1.")
        expected += 1
    if int(data.get("next_clip_index", -1)) != expected:
        raise ValueError("next_clip_index does not follow the accepted clip list.")
    if Path(directory).name != data["name"]:
        raise ValueError("Project folder name and manifest name do not match.")


def project_snapshot(output_directory, project_name):
    data, directory = load_project(output_directory, project_name)
    clips = data["accepted_clips"]
    latest = clips[-1] if clips else {}

    def absolute(relative):
        if not relative:
            return ""
        candidate = (directory / relative).resolve()
        if directory not in candidate.parents:
            raise ValueError("Manifest contains a path outside its project folder.")
        return str(candidate)

    settings = data.get("settings", {})
    prompt = ""
    prompt_relative = latest.get("prompt", "")
    if prompt_relative:
        prompt_path = Path(absolute(prompt_relative))
        if prompt_path.is_file():
            prompt = prompt_path.read_text(encoding="utf-8")
    status = (
        f"{data['name']}: {len(clips)} accepted clip(s); "
        f"next clip {data['next_clip_index']}; revision {data['revision']}"
    )
    return {
        "project_path": str(directory),
        "project_id": str(data["project_id"]),
        "revision": int(data["revision"]),
        "project_token": f"{data['project_id']}:{data['revision']}",
        "next_clip_index": int(data["next_clip_index"]),
        "previous_clip_video": absolute(latest.get("video", "")),
        "previous_context_latent": absolute(latest.get("context", "")),
        "master_audio": absolute(settings.get("master_audio", "")),
        "prompt": prompt,
        "reference_images": list(latest.get("reference_images", [])),
        "status": status,
    }


def project_stamp(output_directory, project_name):
    path = manifest_path(output_directory, project_name)
    if not path.is_file():
        return (str(path), None)
    info = path.stat()
    return (str(path), info.st_size, info.st_mtime_ns)


def list_projects(output_directory):
    root = Path(output_directory).resolve() / PROJECTS_FOLDER
    if not root.is_dir():
        return []
    projects = []
    for directory in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if not directory.is_dir() or not (directory / "project.json").is_file():
            continue
        try:
            snapshot = project_snapshot(output_directory, directory.name)
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        projects.append({
            "name": directory.name,
            "status": snapshot["status"],
            "project_id": snapshot["project_id"],
            "revision": snapshot["revision"],
            "next_clip_index": snapshot["next_clip_index"],
        })
    return projects


def resolve_output_asset(output_directory, value, expected_suffix=None):
    """Resolve an absolute or output-relative asset without leaving output."""
    root = Path(output_directory).resolve()
    raw = Path(str(value).strip().strip('"'))
    candidate = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Asset path is outside the active ComfyUI output folder.")
    if expected_suffix and candidate.suffix.lower() != str(expected_suffix).lower():
        raise ValueError(f"Expected a {expected_suffix} asset, got {candidate.name}.")
    if not candidate.is_file():
        raise FileNotFoundError(f"Project asset does not exist: {candidate}")
    return candidate


def resolve_context_checkpoint(output_directory, filename_prefix, clip_index):
    prefix = str(filename_prefix).replace("\\", "/").strip("/").strip()
    if not prefix:
        raise ValueError("Context checkpoint filename prefix is empty.")
    relative = Path(*prefix.split("/"))
    filename = f"{relative.name}_{int(clip_index):05d}.safetensors"
    return resolve_output_asset(
        output_directory, relative.parent / filename, ".safetensors"
    )


def _copy_atomic(source, destination):
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Accepted clip asset does not exist: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source == destination:
        return
    handle, temporary = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".tmp", dir=str(destination.parent)
    )
    os.close(handle)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def accept_clip(
    output_directory,
    project_name,
    project_token,
    clip_index,
    video_path,
    context_path,
    prompt,
    frame_count,
    overlap_frames,
    audio_mode,
    fps=24.0,
    reference_images=None,
):
    data, directory = load_project(output_directory, project_name)
    expected_token = f"{data['project_id']}:{data['revision']}"
    if str(project_token) != expected_token:
        raise ValueError(
            "Project state changed since this clip was prepared. Reload the project "
            "before accepting it."
        )
    index = int(clip_index)
    if index != int(data["next_clip_index"]):
        raise ValueError(
            f"Project expects clip {data['next_clip_index']}, not clip {index}."
        )
    frames = int(frame_count)
    overlap = int(overlap_frames)
    if frames < 1:
        raise ValueError("Accepted clip must contain at least one frame.")
    if overlap < 0 or overlap >= frames:
        raise ValueError("Overlap must be zero or smaller than the clip frame count.")
    if index == 1 and overlap != 0:
        raise ValueError("The first clip cannot have an incoming overlap.")
    if index > 1 and overlap < 1:
        raise ValueError("A continuation clip must record its incoming overlap.")
    rate = float(fps)
    if rate <= 0:
        raise ValueError("FPS must be positive.")

    video_destination = directory / "clips" / f"clip_{index:05d}.mp4"
    context_destination = directory / "context" / f"clip_{index:05d}.safetensors"
    prompt_destination = directory / "prompts" / f"clip_{index:05d}.txt"

    # Originals remain untouched. The manifest is updated only after both large
    # assets and the prompt have reached their final project locations.
    _copy_atomic(video_path, video_destination)
    _copy_atomic(context_path, context_destination)
    prompt_destination.write_text(str(prompt), encoding="utf-8", newline="\n")

    data["accepted_clips"].append({
        "index": index,
        "video": video_destination.relative_to(directory).as_posix(),
        "context": context_destination.relative_to(directory).as_posix(),
        "prompt": prompt_destination.relative_to(directory).as_posix(),
        "frame_count": frames,
        "overlap_frames": overlap,
        "fps": rate,
        "audio_mode": str(audio_mode),
        # Preserve empty slots so Picture 3 can never shift into Picture 2.
        "reference_images": [str(value) for value in (reference_images or [])],
        "accepted_at": _now(),
    })
    data["next_clip_index"] = index + 1
    data["revision"] = int(data["revision"]) + 1
    data["updated_at"] = _now()
    _write_json_atomic(directory / "project.json", data)
    return project_snapshot(output_directory, project_name)
