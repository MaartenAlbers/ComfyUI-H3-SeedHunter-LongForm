"""Persistent project manifests for H3 SeedHunter long-form productions."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 2
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
            "export": {
                "mode": "delivery_mp4",
                "filename": "",
                "crf": 18,
            },
        },
        "next_clip_index": 1,
        "accepted_clips": [],
        "active_timeline": [],
        "final_render": "",
        "preview_render": "",
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
    if data.get("schema_version") == 1:
        data = _migrate_v1_manifest(data)
        _write_json_atomic(path, data)
    validate_manifest(data, directory)
    return data, directory


def _migrate_v1_manifest(data):
    migrated = dict(data)
    previous = ""
    timeline = []
    clips = []
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, str(data.get("project_id", "seedhunter")))
    for old in data.get("accepted_clips", []):
        clip = dict(old)
        index = int(clip["index"])
        record_id = str(uuid.uuid5(namespace, f"legacy-clip-{index}"))
        clip.update({
            "record_id": record_id,
            "parent_record_id": previous,
            "take": 1,
        })
        clips.append(clip)
        timeline.append(record_id)
        previous = record_id
    migrated["schema_version"] = SCHEMA_VERSION
    migrated["accepted_clips"] = clips
    migrated["active_timeline"] = timeline
    migrated["next_clip_index"] = len(timeline) + 1
    migrated["revision"] = int(migrated.get("revision", 0)) + 1
    migrated["updated_at"] = _now()
    return migrated


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
    records = {}
    for clip in clips:
        if not isinstance(clip, dict) or not clip.get("record_id"):
            raise ValueError("Every accepted clip must have a record_id.")
        if clip["record_id"] in records:
            raise ValueError("Accepted clip record_ids must be unique.")
        records[clip["record_id"]] = clip
    timeline = data.get("active_timeline")
    if not isinstance(timeline, list):
        raise ValueError("project.json active_timeline must be a list.")
    previous = ""
    for expected, record_id in enumerate(timeline, start=1):
        clip = records.get(record_id)
        if clip is None:
            raise ValueError("Active timeline references an unknown clip record.")
        if int(clip.get("index", -1)) != expected:
            raise ValueError("Active timeline clips must be numbered consecutively.")
        if str(clip.get("parent_record_id", "")) != previous:
            raise ValueError("Active timeline contains a broken parent chain.")
        previous = record_id
    if int(data.get("next_clip_index", -1)) != len(timeline) + 1:
        raise ValueError("next_clip_index does not follow the active timeline.")
    if Path(directory).name != data["name"]:
        raise ValueError("Project folder name and manifest name do not match.")


def project_snapshot(output_directory, project_name):
    data, directory = load_project(output_directory, project_name)
    clips = data["accepted_clips"]
    records = {clip["record_id"]: clip for clip in clips}
    timeline_ids = data["active_timeline"]
    timeline = [records[record_id] for record_id in timeline_ids]
    latest = timeline[-1] if timeline else {}

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
        f"{data['name']}: {len(timeline)} active / {len(clips)} stored clip(s); "
        f"next clip {data['next_clip_index']}; revision {data['revision']}"
    )
    clip_choices = [
        {
            "record_id": clip["record_id"],
            "index": int(clip["index"]),
            "take": int(clip.get("take", 1)),
            "active": clip["record_id"] in timeline_ids,
            "label": f"Clip {clip['index']} · Take {clip.get('take', 1)}",
        }
        for clip in clips
    ]
    return {
        "project_path": str(directory),
        "project_id": str(data["project_id"]),
        "revision": int(data["revision"]),
        "project_token": f"{data['project_id']}:{data['revision']}",
        "next_clip_index": int(data["next_clip_index"]),
        "previous_clip_video": absolute(latest.get("video", "")),
        "previous_context_latent": absolute(latest.get("context", "")),
        "master_audio": absolute(settings.get("master_audio", "")),
        "final_render": absolute(data.get("final_render", "")),
        "preview_render": absolute(data.get("preview_render", "")),
        "export_settings": dict(settings.get("export", {})),
        "workflow_settings": dict(settings.get("workflow", {})),
        "prompt": prompt,
        "reference_images": list(latest.get("reference_images", [])),
        "active_head_id": latest.get("record_id", ""),
        "clip_choices": clip_choices,
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


def checkout_clip(output_directory, project_name, project_token, record_id):
    data, directory = load_project(output_directory, project_name)
    expected_token = f"{data['project_id']}:{data['revision']}"
    if str(project_token) != expected_token:
        raise ValueError("Project state changed. Reload it before changing timeline.")
    records = {clip["record_id"]: clip for clip in data["accepted_clips"]}
    wanted = str(record_id)
    if wanted and wanted not in records:
        raise ValueError("Selected continuation clip does not exist in this project.")
    timeline = []
    seen = set()
    current = wanted
    while current:
        if current in seen:
            raise ValueError("Clip ancestry contains a cycle.")
        seen.add(current)
        clip = records[current]
        timeline.append(current)
        current = str(clip.get("parent_record_id", ""))
    timeline.reverse()
    data["active_timeline"] = timeline
    data["next_clip_index"] = len(timeline) + 1
    data["revision"] = int(data["revision"]) + 1
    data["updated_at"] = _now()
    _write_json_atomic(directory / "project.json", data)
    return project_snapshot(output_directory, project_name)


def _clean_workflow_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError("Workflow settings must be a JSON object.")
    cleaned = {}
    numeric = {
        "clip_seconds": (0.1, 3600.0),
        "preview_megapixels": (0.1, 4.0),
        "single_pass_megapixels": (0.1, 4.0),
        "final_pass_megapixels": (0.1, 4.0),
        "context_frames": (1, 9999),
    }
    for name, (minimum, maximum) in numeric.items():
        if name not in settings:
            continue
        value = float(settings[name])
        if not minimum <= value <= maximum:
            raise ValueError(f"Project setting {name} is outside its valid range.")
        cleaned[name] = int(value) if name == "context_frames" else value
    if "audio_mode" in settings:
        mode = str(settings["audio_mode"])
        if mode not in ("locked audio", "audio reference", "generate audio", "silent audio"):
            raise ValueError("Project contains an unknown audio mode.")
        cleaned["audio_mode"] = mode
    if "run_mode" in settings:
        mode = str(settings["run_mode"])
        if mode not in ("preview", "single"):
            raise ValueError("Project run mode must be preview or single.")
        cleaned["run_mode"] = mode
    if "aspect_ratio" in settings:
        aspect = str(settings["aspect_ratio"])
        allowed = {
            "1:1 (Square)", "2:3 (Portrait Photo)", "3:2 (Photo)",
            "3:4 (Portrait Standard)", "4:3 (Standard)",
            "9:16 (Portrait Widescreen)", "16:9 (Widescreen)",
            "21:9 (Ultrawide)",
        }
        if aspect not in allowed:
            raise ValueError("Project contains an unknown aspect ratio.")
        cleaned["aspect_ratio"] = aspect
    return cleaned


def save_project_settings(output_directory, project_name, project_token, settings):
    data, directory = load_project(output_directory, project_name)
    expected_token = f"{data['project_id']}:{data['revision']}"
    if str(project_token) != expected_token:
        raise ValueError("Project state changed. Reload it before saving settings.")
    data.setdefault("settings", {})["workflow"] = _clean_workflow_settings(settings)
    data["revision"] = int(data["revision"]) + 1
    data["updated_at"] = _now()
    _write_json_atomic(directory / "project.json", data)
    return project_snapshot(output_directory, project_name)


def _active_records(data):
    records = {item["record_id"]: item for item in data["accepted_clips"]}
    return [records[record_id] for record_id in data["active_timeline"]]


def _inside(directory, relative):
    candidate = (directory / str(relative)).resolve()
    if directory not in candidate.parents:
        raise ValueError("Manifest contains a path outside its project folder.")
    return candidate


def _clean_export_settings(settings):
    settings = settings or {}
    if not isinstance(settings, dict):
        raise ValueError("Export settings must be a JSON object.")
    mode = str(settings.get("mode", "delivery_mp4"))
    if mode not in ("delivery_mp4", "master_prores"):
        raise ValueError("Unknown timeline export mode.")
    filename = str(settings.get("filename", "")).strip()
    if filename:
        if "/" in filename or "\\" in filename:
            raise ValueError("Export filename cannot contain a folder path.")
        filename = Path(filename).stem
        if not _SAFE_NAME.fullmatch(filename) or filename in (".", ".."):
            raise ValueError("Export filename contains unsupported characters.")
    crf = int(settings.get("crf", 18))
    if not 0 <= crf <= 30:
        raise ValueError("Delivery CRF must be between 0 and 30.")
    return {"mode": mode, "filename": filename, "crf": crf}


def assemble_project(output_directory, project_name, project_token, export_settings=None):
    """Render the active timeline with frame-exact video and audio overlaps."""
    data, directory = load_project(output_directory, project_name)
    expected_token = f"{data['project_id']}:{data['revision']}"
    if str(project_token) != expected_token:
        raise ValueError("Project state changed. Reload it before assembling.")
    records = _active_records(data)
    if not records:
        raise ValueError("Accept at least one clip before assembling the project.")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("FFmpeg was not found on PATH.")

    paths = []
    for record in records:
        path = _inside(directory, record.get("video", ""))
        if not path.is_file():
            raise FileNotFoundError(f"Accepted clip is missing: {path.name}")
        paths.append(path)

    fps = float(records[0].get("fps", 24.0))
    if fps <= 0 or any(abs(float(item.get("fps", fps)) - fps) > 0.001 for item in records):
        raise ValueError("All active clips must use the same positive FPS.")
    filters = []
    video_parts = []
    for index, record in enumerate(records):
        frames = int(record.get("frame_count", 0))
        incoming = int(record.get("overlap_frames", 0)) if index else 0
        outgoing = int(records[index + 1].get("overlap_frames", 0)) if index + 1 < len(records) else 0
        if frames < 1 or incoming < 0 or outgoing < 0 or incoming + outgoing >= frames:
            raise ValueError("Timeline overlap metadata does not fit its clip frames.")
        unique_end = frames - outgoing
        if unique_end > incoming:
            label = f"u{index}"
            filters.append(
                f"[{index}:v]trim=start_frame={incoming}:end_frame={unique_end},"
                f"setpts=PTS-STARTPTS[{label}]"
            )
            video_parts.append(f"[{label}]")
        if outgoing:
            left = f"ol{index}"
            right = f"ir{index + 1}"
            blend = f"b{index}_{index + 1}"
            filters.append(
                f"[{index}:v]trim=start_frame={frames - outgoing}:end_frame={frames},"
                f"setpts=PTS-STARTPTS[{left}]"
            )
            filters.append(
                f"[{index + 1}:v]trim=start_frame=0:end_frame={outgoing},"
                f"setpts=PTS-STARTPTS[{right}]"
            )
            expression = "B" if outgoing == 1 else f"A*(1-N/{outgoing - 1})+B*(N/{outgoing - 1})"
            filters.append(
                f"[{left}][{right}]blend=all_expr='{expression}':shortest=1,"
                f"setpts=PTS-STARTPTS[{blend}]"
            )
            video_parts.append(f"[{blend}]")
    filters.append("".join(video_parts) + f"concat=n={len(video_parts)}:v=1:a=0[v]")

    audio_parts = []
    for index, record in enumerate(records):
        overlap = int(record.get("overlap_frames", 0)) if index else 0
        start = overlap / fps
        label = f"a{index}"
        filters.append(
            f"[{index}:a]aresample=32000,atrim=start={start:.12g},"
            f"asetpts=PTS-STARTPTS[{label}]"
        )
        audio_parts.append(f"[{label}]")
    total_frames = sum(int(item["frame_count"]) for item in records) - sum(
        int(item.get("overlap_frames", 0)) for item in records[1:]
    )
    total_seconds = total_frames / fps
    filters.append(
        "".join(audio_parts) + f"concat=n={len(audio_parts)}:v=0:a=1,"
        f"apad=whole_dur={total_seconds:.12g},atrim=duration={total_seconds:.12g}[a]"
    )

    renders = directory / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    export = _clean_export_settings(export_settings or data.get("settings", {}).get("export", {}))
    stem = export["filename"] or f"{validate_project_name(project_name)}_timeline_r{data['revision']}"
    master = export["mode"] == "master_prores"
    destination = renders / f"{stem}{'.mov' if master else '.mp4'}"
    temporary = destination.with_name(f".{destination.stem}.partial{destination.suffix}")
    preview = renders / f"{stem}_preview.mp4" if master else destination
    preview_temporary = preview.with_name(f".{preview.stem}.partial.mp4") if master else temporary
    command = [ffmpeg, "-y", "-v", "warning"]
    for path in paths:
        command.extend(("-i", str(path)))
    command.extend(("-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]", "-r", f"{fps:.12g}"))
    if master:
        command.extend((
            "-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le",
            "-c:a", "pcm_s24le", str(temporary),
        ))
    else:
        command.extend((
            "-c:v", "libx264", "-preset", "medium", "-crf", str(export["crf"]),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(temporary),
        ))
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        os.replace(temporary, destination)
        if master:
            proxy_command = [
                ffmpeg, "-y", "-v", "warning", "-i", str(destination),
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(preview_temporary),
            ]
            subprocess.run(proxy_command, check=True, capture_output=True, text=True)
            os.replace(preview_temporary, preview)
    except subprocess.CalledProcessError as exc:
        temporary.unlink(missing_ok=True)
        if master:
            preview_temporary.unlink(missing_ok=True)
        detail = (exc.stderr or exc.stdout or "FFmpeg failed.").strip().splitlines()[-1]
        raise OSError(f"Project assembly failed: {detail}") from exc

    data["final_render"] = destination.relative_to(directory).as_posix()
    data["preview_render"] = preview.relative_to(directory).as_posix()
    data.setdefault("settings", {})["export"] = export
    data["revision"] = int(data["revision"]) + 1
    data["updated_at"] = _now()
    _write_json_atomic(directory / "project.json", data)
    snapshot = project_snapshot(output_directory, project_name)
    snapshot["final_render"] = str(destination.resolve())
    snapshot["preview_render"] = str(preview.resolve())
    snapshot["final_frame_count"] = total_frames
    snapshot["final_duration"] = total_seconds
    return snapshot


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
    workflow_settings=None,
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

    parent = data["active_timeline"][-1] if data["active_timeline"] else ""
    take = 1 + sum(
        1 for clip in data["accepted_clips"]
        if int(clip.get("index", -1)) == index
        and str(clip.get("parent_record_id", "")) == parent
    )
    record_id = str(uuid.uuid4())
    stem = f"clip_{index:05d}_take_{take:03d}"
    video_destination = directory / "clips" / f"{stem}.mp4"
    context_destination = directory / "context" / f"{stem}.safetensors"
    prompt_destination = directory / "prompts" / f"{stem}.txt"

    # Originals remain untouched. The manifest is updated only after both large
    # assets and the prompt have reached their final project locations.
    _copy_atomic(video_path, video_destination)
    _copy_atomic(context_path, context_destination)
    prompt_destination.write_text(str(prompt), encoding="utf-8", newline="\n")

    data["accepted_clips"].append({
        "record_id": record_id,
        "parent_record_id": parent,
        "index": index,
        "take": take,
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
    data["active_timeline"].append(record_id)
    if workflow_settings is not None:
        data.setdefault("settings", {})["workflow"] = _clean_workflow_settings(
            workflow_settings
        )
    data["next_clip_index"] = index + 1
    data["revision"] = int(data["revision"]) + 1
    data["updated_at"] = _now()
    _write_json_atomic(directory / "project.json", data)
    return project_snapshot(output_directory, project_name)
