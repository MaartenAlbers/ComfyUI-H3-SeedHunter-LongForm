import json
import tempfile
import unittest
from pathlib import Path

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
