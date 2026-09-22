import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import project_state


class ProjectStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_create_and_load_project(self):
        data, directory = project_state.create_project(self.output, "Film One")
        self.assertEqual(data["revision"], 1)
        self.assertEqual(data["next_clip_index"], 1)
        self.assertTrue((directory / "media" / "references").is_dir())
        self.assertTrue((directory / "renders").is_dir())

        snapshot = project_state.project_snapshot(self.output, "Film One")
        self.assertEqual(snapshot["project_id"], data["project_id"])
        self.assertEqual(snapshot["project_token"], f"{data['project_id']}:1")
        self.assertEqual(snapshot["previous_clip_video"], "")

    def test_duplicate_project_is_rejected(self):
        project_state.create_project(self.output, "Film One")
        with self.assertRaises(FileExistsError):
            project_state.create_project(self.output, "Film One")

    def test_unsafe_names_are_rejected(self):
        for name in ("", "../escape", "folder/name", "folder\\name"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                project_state.project_directory(self.output, name)

    def test_manifest_requires_consecutive_clips(self):
        _, directory = project_state.create_project(self.output, "Film One")
        path = directory / "project.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["accepted_clips"] = [{
            "record_id": "record-2", "parent_record_id": "", "index": 2,
        }]
        data["active_timeline"] = ["record-2"]
        data["next_clip_index"] = 3
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "consecutively"):
            project_state.load_project(self.output, "Film One")

    def test_manifest_paths_cannot_escape_project(self):
        _, directory = project_state.create_project(self.output, "Film One")
        path = directory / "project.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["accepted_clips"] = [{
            "record_id": "record-1",
            "parent_record_id": "",
            "index": 1,
            "video": "../../outside.mp4",
            "context": "context/clip_00001.safetensors",
        }]
        data["active_timeline"] = ["record-1"]
        data["next_clip_index"] = 2
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside"):
            project_state.project_snapshot(self.output, "Film One")

    def test_accept_clip_copies_pair_and_advances_revision(self):
        data, directory = project_state.create_project(self.output, "Film One")
        source_video = self.output / "render.mp4"
        source_context = self.output / "render.safetensors"
        source_video.write_bytes(b"video")
        source_context.write_bytes(b"latent")

        snapshot = project_state.accept_clip(
            self.output,
            "Film One",
            f"{data['project_id']}:1",
            1,
            source_video,
            source_context,
            "A test prompt",
            243,
            0,
            "locked audio",
            24.0,
            ["hero.png", "wardrobe.png"],
        )

        self.assertEqual(snapshot["revision"], 2)
        self.assertEqual(snapshot["next_clip_index"], 2)
        self.assertEqual(Path(snapshot["previous_clip_video"]).read_bytes(), b"video")
        self.assertEqual(Path(snapshot["previous_context_latent"]).read_bytes(), b"latent")
        self.assertEqual(
            (directory / "prompts" / "clip_00001_take_001.txt").read_text(encoding="utf-8"),
            "A test prompt",
        )
        self.assertEqual(snapshot["prompt"], "A test prompt")
        self.assertEqual(snapshot["reference_images"], ["hero.png", "wardrobe.png"])

    def test_accept_clip_rejects_stale_project_token(self):
        data, _ = project_state.create_project(self.output, "Film One")
        video = self.output / "render.mp4"
        context = self.output / "render.safetensors"
        video.write_bytes(b"video")
        context.write_bytes(b"latent")
        with self.assertRaisesRegex(ValueError, "state changed"):
            project_state.accept_clip(
                self.output, "Film One", f"{data['project_id']}:0", 1,
                video, context, "", 243, 0, "locked audio", 24.0,
            )

    def test_save_and_restore_project_workflow_settings(self):
        data, _ = project_state.create_project(self.output, "Film One")
        settings = {
            "clip_seconds": 8.5,
            "preview_megapixels": 0.6,
            "single_pass_megapixels": 1.8,
            "final_pass_megapixels": 1.5,
            "aspect_ratio": "9:16 (Portrait Widescreen)",
            "context_frames": 56,
            "audio_mode": "generate audio",
            "run_mode": "single",
        }

        snapshot = project_state.save_project_settings(
            self.output, "Film One", f"{data['project_id']}:1", settings
        )

        self.assertEqual(snapshot["revision"], 2)
        self.assertEqual(snapshot["workflow_settings"], settings)
        reloaded = project_state.project_snapshot(self.output, "Film One")
        self.assertEqual(reloaded["workflow_settings"], settings)

    def test_accept_clip_automatically_saves_workflow_settings(self):
        data, _ = project_state.create_project(self.output, "Film One")
        video = self.output / "render.mp4"
        context = self.output / "render.safetensors"
        video.write_bytes(b"video")
        context.write_bytes(b"latent")
        settings = {
            "clip_seconds": 6.0,
            "preview_megapixels": 0.5,
            "single_pass_megapixels": 1.5,
            "context_frames": 39,
            "audio_mode": "audio reference",
            "run_mode": "preview",
        }

        snapshot = project_state.accept_clip(
            self.output, "Film One", f"{data['project_id']}:1", 1,
            video, context, "Prompt", 243, 0, "audio reference", 24.0,
            [], settings,
        )

        self.assertEqual(snapshot["workflow_settings"], settings)

    def test_invalid_project_workflow_setting_is_rejected(self):
        data, _ = project_state.create_project(self.output, "Film One")
        with self.assertRaisesRegex(ValueError, "outside its valid range"):
            project_state.save_project_settings(
                self.output,
                "Film One",
                f"{data['project_id']}:1",
                {"clip_seconds": 0},
            )

    def test_assemble_active_timeline_uses_recorded_frame_overlaps(self):
        data, directory = project_state.create_project(self.output, "Film One")
        manifest_path = directory / "project.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        records = []
        previous = ""
        for index, overlap in ((1, 0), (2, 39), (3, 39)):
            record_id = f"record-{index}"
            video = directory / "clips" / f"clip_{index:05d}.mp4"
            video.write_bytes(b"video")
            records.append({
                "record_id": record_id,
                "parent_record_id": previous,
                "index": index,
                "take": 1,
                "video": video.relative_to(directory).as_posix(),
                "context": f"context/clip_{index:05d}.safetensors",
                "prompt": f"prompts/clip_{index:05d}.txt",
                "frame_count": 124,
                "overlap_frames": overlap,
                "fps": 24.0,
            })
            previous = record_id
        manifest["accepted_clips"] = records
        manifest["active_timeline"] = [item["record_id"] for item in records]
        manifest["next_clip_index"] = 4
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        command = []

        def fake_run(args, **kwargs):
            command.extend(args)
            Path(args[-1]).write_bytes(b"assembled")
            return mock.Mock(returncode=0, stderr="", stdout="")

        with mock.patch.object(project_state.shutil, "which", return_value="ffmpeg"), \
                mock.patch.object(project_state.subprocess, "run", side_effect=fake_run):
            snapshot = project_state.assemble_project(
                self.output, "Film One", f"{data['project_id']}:1"
            )

        filter_graph = command[command.index("-filter_complex") + 1]
        self.assertIn("N/38", filter_graph)
        self.assertIn("concat=n=5:v=1:a=0", filter_graph)
        self.assertIn("atrim=start=1.625", filter_graph)
        self.assertIn("concat=n=3:v=0:a=1", filter_graph)
        self.assertNotIn("acrossfade", filter_graph)
        self.assertEqual(snapshot["final_frame_count"], 294)
        self.assertAlmostEqual(snapshot["final_duration"], 12.25)
        self.assertEqual(snapshot["revision"], 2)
        self.assertEqual(Path(snapshot["final_render"]).read_bytes(), b"assembled")
        self.assertEqual(snapshot["preview_render"], snapshot["final_render"])
        self.assertIn("libx264", command)
        self.assertEqual(command[command.index("-crf") + 1], "18")

    def test_master_export_uses_prores_pcm_and_creates_preview_proxy(self):
        data, directory = project_state.create_project(self.output, "Film One")
        manifest_path = directory / "project.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        video = directory / "clips" / "clip_00001.mp4"
        video.write_bytes(b"video")
        manifest["accepted_clips"] = [{
            "record_id": "record-1", "parent_record_id": "", "index": 1,
            "take": 1, "video": "clips/clip_00001.mp4",
            "context": "context/clip_00001.safetensors",
            "prompt": "prompts/clip_00001.txt", "frame_count": 124,
            "overlap_frames": 0, "fps": 24.0,
        }]
        manifest["active_timeline"] = ["record-1"]
        manifest["next_clip_index"] = 2
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        commands = []

        def fake_run(args, **kwargs):
            commands.append(list(args))
            Path(args[-1]).write_bytes(b"render")
            return mock.Mock(returncode=0, stderr="", stdout="")

        with mock.patch.object(project_state.shutil, "which", return_value="ffmpeg"), \
                mock.patch.object(project_state.subprocess, "run", side_effect=fake_run):
            snapshot = project_state.assemble_project(
                self.output, "Film One", f"{data['project_id']}:1",
                {"mode": "master_prores", "filename": "My Master", "crf": 18},
            )

        self.assertEqual(len(commands), 2)
        self.assertIn("prores_ks", commands[0])
        self.assertIn("pcm_s24le", commands[0])
        self.assertIn("libx264", commands[1])
        self.assertTrue(snapshot["final_render"].endswith("My Master.mov"))
        self.assertTrue(snapshot["preview_render"].endswith("My Master_preview.mp4"))
        self.assertEqual(snapshot["export_settings"]["mode"], "master_prores")

    def test_export_settings_reject_paths_and_unknown_modes(self):
        for settings in ({"mode": "unknown"}, {"filename": "../escape"}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                project_state._clean_export_settings(settings)

    def test_continuation_requires_overlap(self):
        data, _ = project_state.create_project(self.output, "Film One")
        video = self.output / "render.mp4"
        context = self.output / "render.safetensors"
        video.write_bytes(b"video")
        context.write_bytes(b"latent")
        first = project_state.accept_clip(
            self.output, "Film One", f"{data['project_id']}:1", 1,
            video, context, "", 243, 0, "locked audio", 24.0,
        )
        with self.assertRaisesRegex(ValueError, "incoming overlap"):
            project_state.accept_clip(
                self.output, "Film One", first["project_token"], 2,
                video, context, "", 243, 0, "locked audio", 24.0,
            )

    def test_output_asset_and_context_checkpoint_resolution(self):
        checkpoint = self.output / "h3_resume" / "chain" / "clip_00003.safetensors"
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_bytes(b"latent")
        resolved = project_state.resolve_context_checkpoint(
            self.output, "h3_resume/chain/clip", 3
        )
        self.assertEqual(resolved, checkpoint.resolve())

    def test_output_asset_cannot_escape_output(self):
        outside = self.output.parent / "outside.mp4"
        outside.write_bytes(b"video")
        try:
            with self.assertRaisesRegex(ValueError, "outside"):
                project_state.resolve_output_asset(self.output, outside, ".mp4")
        finally:
            outside.unlink(missing_ok=True)

    def test_list_projects_returns_only_valid_manifests(self):
        first, _ = project_state.create_project(self.output, "Zulu")
        second, _ = project_state.create_project(self.output, "Alpha")
        invalid = self.output / project_state.PROJECTS_FOLDER / "Broken"
        invalid.mkdir()
        (invalid / "project.json").write_text("not json", encoding="utf-8")

        projects = project_state.list_projects(self.output)
        self.assertEqual([item["name"] for item in projects], ["Alpha", "Zulu"])
        self.assertEqual(
            {item["project_id"] for item in projects},
            {first["project_id"], second["project_id"]},
        )

    def test_checkout_preserves_descendants_and_creates_new_take(self):
        data, _ = project_state.create_project(self.output, "Film One")
        video = self.output / "render.mp4"
        context = self.output / "render.safetensors"
        video.write_bytes(b"video")
        context.write_bytes(b"latent")
        snapshot = None
        for index in range(1, 6):
            token = f"{data['project_id']}:1" if snapshot is None else snapshot["project_token"]
            snapshot = project_state.accept_clip(
                self.output, "Film One", token, index, video, context,
                f"Prompt {index}", 243, 0 if index == 1 else 39,
                "generate audio", 24.0,
            )

        clip3 = next(item for item in snapshot["clip_choices"] if item["index"] == 3)
        rewound = project_state.checkout_clip(
            self.output, "Film One", snapshot["project_token"], clip3["record_id"]
        )
        self.assertEqual(rewound["next_clip_index"], 4)
        self.assertIn("3 active / 5 stored", rewound["status"])

        branched = project_state.accept_clip(
            self.output, "Film One", rewound["project_token"], 4,
            video, context, "Alternative 4", 243, 39,
            "generate audio", 24.0,
        )
        alternatives = [
            item for item in branched["clip_choices"] if item["index"] == 4
        ]
        self.assertEqual([item["take"] for item in alternatives], [1, 2])
        self.assertTrue(Path(branched["previous_clip_video"]).name.endswith("take_002.mp4"))

    def test_schema_one_project_migrates_without_losing_clip(self):
        data, directory = project_state.create_project(self.output, "Film One")
        path = directory / "project.json"
        data["schema_version"] = 1
        data.pop("active_timeline")
        data["accepted_clips"] = [{
            "index": 1,
            "video": "clips/clip_00001.mp4",
            "context": "context/clip_00001.safetensors",
            "prompt": "prompts/clip_00001.txt",
        }]
        data["next_clip_index"] = 2
        path.write_text(json.dumps(data), encoding="utf-8")

        migrated, _ = project_state.load_project(self.output, "Film One")
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(len(migrated["active_timeline"]), 1)
        self.assertEqual(migrated["next_clip_index"], 2)
        self.assertEqual(migrated["accepted_clips"][0]["take"], 1)


if __name__ == "__main__":
    unittest.main()
