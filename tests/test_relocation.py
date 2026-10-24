from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from playlist_relocate import PlaylistError, plan_relocation, write_plan
from playlist_relocate.cli import main


class RelocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.library = self.root / "library"
        (self.library / "Artist").mkdir(parents=True)
        (self.library / "Artist" / "Tone.wav").write_bytes(b"audio fixture")
        self.source = self.root / "old.m3u8"
        self.mapping = self.root / "map.json"
        self.output = self.root / "new.m3u8"
        self.source.write_text(
            "#EXTM3U\n#EXTINF:1,Private title\nM:\\Music\\Artist\\Tone.wav\n", encoding="utf-8"
        )
        self.config = {
            "version": 1,
            "source_style": "windows",
            "source_base": "M:\\Music\\Lists",
            "mappings": [{"from": "M:\\Music", "to": "library"}],
        }
        self.save_config()

    def save_config(self):
        self.mapping.write_text(json.dumps(self.config), encoding="utf-8")

    def plan(self, **options):
        self.save_config()
        return plan_relocation(self.source, self.mapping, self.output, **options)

    def test_preview_then_write_preserves_order_comments_and_inputs(self):
        before = [hashlib.sha256(p.read_bytes()).digest() for p in (self.source, self.mapping)]
        plan = self.plan()
        self.assertEqual(plan.report["status"], "ready")
        self.assertFalse(self.output.exists())
        self.assertEqual(
            plan.content.decode(), "#EXTM3U\n#EXTINF:1,Private title\nlibrary/Artist/Tone.wav\n"
        )
        result = write_plan(plan)
        self.assertEqual(result["status"], "written")
        self.assertTrue((self.output.parent / self.output.read_text().splitlines()[-1]).is_file())
        self.assertEqual(
            before, [hashlib.sha256(p.read_bytes()).digest() for p in (self.source, self.mapping)]
        )

    def test_windows_source_matches_prefix_case_insensitively(self):
        self.source.write_text("m:/music/Artist/Tone.wav\n", encoding="utf-8")
        self.assertEqual(self.plan().report["resolved"], 1)

    def test_prefix_component_boundary(self):
        self.source.write_text("M:\\MusicOther\\Artist\\Tone.wav\n", encoding="utf-8")
        self.assertEqual(self.plan().report["findings"][0]["code"], "unmapped_source")

    def test_longest_prefix_wins(self):
        other = self.root / "other"
        other.mkdir()
        (other / "Tone.wav").write_bytes(b"preferred")
        self.config["mappings"].append({"from": "M:\\Music\\Artist", "to": "other"})
        self.assertEqual(self.plan().content.decode().splitlines()[-1], "other/Tone.wav")

    def test_posix_source_on_any_host(self):
        self.config.update(source_style="posix", source_base="/old/music/playlists")
        self.config["mappings"] = [{"from": "/old/music", "to": "library"}]
        self.source.write_text("/old/music/Artist/Tone.wav\n", encoding="utf-8")
        self.assertEqual(self.plan().report["status"], "ready")

    def test_relative_source_and_dotdot_normalization(self):
        self.source.write_text("../Artist/./Tone.wav\n", encoding="utf-8")
        self.assertEqual(self.plan().report["status"], "ready")

    def test_relative_source_requires_explicit_base(self):
        del self.config["source_base"]
        self.source.write_text("Artist/Tone.wav\n", encoding="utf-8")
        self.assertEqual(
            self.plan().report["findings"][0]["code"], "relative_path_needs_source_base"
        )

    def test_unc_source_is_lexical(self):
        self.config["mappings"] = [{"from": "\\\\old-server\\share\\Music", "to": "library"}]
        self.source.write_text("\\\\old-server\\share\\Music\\Artist\\Tone.wav\n", encoding="utf-8")
        self.assertEqual(self.plan().report["status"], "ready")

    def test_duplicate_tracks_preserved(self):
        self.source.write_text("M:\\Music\\Artist\\Tone.wav\n" * 3, encoding="utf-8")
        plan = self.plan()
        self.assertEqual(plan.report["entries"], 3)
        self.assertEqual(plan.content.decode().splitlines(), ["library/Artist/Tone.wav"] * 3)

    def test_distinct_sources_cannot_collapse_to_same_target(self):
        self.config["mappings"].append({"from": "N:\\Other", "to": "library"})
        self.source.write_text(
            "M:\\Music\\Artist\\Tone.wav\nN:\\Other\\Artist\\Tone.wav\n", encoding="utf-8"
        )
        self.assertEqual(self.plan().report["findings"][0]["code"], "target_collision")

    def test_missing_target_blocks_every_write(self):
        self.source.write_text(
            "M:\\Music\\Artist\\Tone.wav\nM:\\Music\\Absent.wav\n", encoding="utf-8"
        )
        plan = self.plan()
        self.assertIsNone(plan.content)
        with self.assertRaisesRegex(PlaylistError, "plan_blocked"):
            write_plan(plan)
        self.assertFalse(self.output.exists())

    def test_hardlink_alias_collision_is_detected(self):
        os.link(self.library / "Artist" / "Tone.wav", self.library / "Alias.wav")
        self.source.write_text(
            "M:\\Music\\Artist\\Tone.wav\nM:\\Music\\Alias.wav\n", encoding="utf-8"
        )
        self.assertEqual(self.plan().report["findings"][0]["code"], "target_collision")

    def test_unrepresentable_output_is_a_clean_error(self):
        with self.assertRaises(PlaylistError):
            plan_relocation(self.source, self.mapping, "bad\x00name")

    def test_directory_is_not_media_file(self):
        self.source.write_text("M:\\Music\\Artist\n", encoding="utf-8")
        self.assertEqual(self.plan().report["findings"][0]["code"], "target_not_regular_file")

    def test_source_traversal_cannot_escape_mapping(self):
        self.source.write_text("M:\\Music\\..\\secret.wav\n", encoding="utf-8")
        self.assertEqual(self.plan().report["findings"][0]["code"], "unmapped_source")
        self.source.write_text("M:\\..\\secret.wav\n", encoding="utf-8")
        self.assertEqual(self.plan().report["findings"][0]["code"], "source_root_escape")

    def test_target_symlink_escape(self):
        secret = self.root / "outside.wav"
        secret.write_bytes(b"outside")
        try:
            (self.library / "escape.wav").symlink_to(secret)
        except OSError:
            self.skipTest("Symlink creation not available to this OS user")
        self.source.write_text("M:\\Music\\escape.wav\n", encoding="utf-8")
        self.assertEqual(self.plan().report["findings"][0]["code"], "target_root_escape")

    def test_existing_output_and_input_protected(self):
        self.output.write_text("KEEP", encoding="utf-8")
        with self.assertRaisesRegex(PlaylistError, "output_exists"):
            self.plan()
        self.assertEqual(self.output.read_text(), "KEEP")
        with self.assertRaises(PlaylistError):
            plan_relocation(self.source, self.mapping, self.source)

    def test_late_output_creation_cannot_be_overwritten(self):
        plan = self.plan()
        self.output.write_text("KEEP", encoding="utf-8")
        with self.assertRaisesRegex(PlaylistError, "output_exists"):
            write_plan(plan)
        self.assertEqual(self.output.read_text(), "KEEP")
        self.assertEqual(list(self.root.glob(".playlist-relocate-*")), [])

    def test_atomic_publish_failure_does_not_leave_output(self):
        plan = self.plan()
        with patch("playlist_relocate.core.os.link", side_effect=OSError("private path")):
            with self.assertRaisesRegex(PlaylistError, "atomic_publish_failed"):
                write_plan(plan)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".playlist-relocate-*")), [])

    def test_absolute_output(self):
        line = self.plan(absolute=True).content.decode().splitlines()[-1]
        actual = Path(line)
        expected = self.library / "Artist" / "Tone.wav"
        self.assertTrue(actual.is_absolute())
        self.assertTrue(actual.samefile(expected))
        self.assertEqual(actual.read_bytes(), b"audio fixture")

    def test_blank_lines_crlf_and_bom(self):
        self.source.write_bytes(b"\xef\xbb\xbf#EXTM3U\r\n\r\nM:\\Music\\Artist\\Tone.wav\r\n")
        self.assertEqual(self.plan().content.decode(), "#EXTM3U\n\nlibrary/Artist/Tone.wav\n")

    def test_unicode_and_percent_are_literal(self):
        (self.library / "音楽%20.wav").write_bytes(b"fixture")
        self.source.write_text("M:\\Music\\音楽%20.wav\n", encoding="utf-8")
        self.assertIn("音楽%20.wav", self.plan().content.decode())

    def test_leading_hash_output_is_disambiguated(self):
        (self.library / "#tone.wav").write_bytes(b"fixture")
        self.source.write_text("M:\\Music\\#tone.wav\n", encoding="utf-8")
        self.output = self.library / "new.m3u8"
        self.assertEqual(self.plan().content.decode(), "./#tone.wav\n")

    def test_uris_partial_roots_and_devices_rejected(self):
        for entry in [
            "https://example.test/a.mp3",
            "file:///music/a.mp3",
            "M:relative.wav",
            "\\Artist\\Tone.wav",
            "\\\\?\\M:\\Music\\Tone.wav",
            "M:\\Music\\CON.wav",
            " M:\\Music\\Artist\\Tone.wav ",
        ]:
            with self.subTest(entry=entry):
                self.source.write_text(entry + "\n", encoding="utf-8")
                self.assertEqual(self.plan().report["status"], "blocked")

    def test_hls_and_empty_rejected(self):
        for text, code in [
            ("#EXTM3U\n#EXT-X-VERSION:3\n", "hls_not_supported"),
            ("#EXTM3U\n", "empty_playlist"),
        ]:
            self.source.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(PlaylistError, code):
                self.plan()

    def test_oversized_bad_encoding_and_controls(self):
        for raw, code in [(b"\xff", "not_utf8"), (b"\x00", "control_character")]:
            self.source.write_bytes(raw)
            with self.assertRaisesRegex(PlaylistError, code):
                self.plan()
        self.source.write_bytes(b"longer")
        with self.assertRaisesRegex(PlaylistError, "size_limit"):
            self.plan(max_bytes=2)

    def test_limits_and_complete_counts(self):
        self.source.write_text("M:\\Music\\absent.wav\n" * 20, encoding="utf-8")
        plan = self.plan(max_findings=1)
        self.assertEqual(plan.report["issue_count"], 20)
        self.assertEqual(len(plan.report["findings"]), 1)
        self.assertTrue(plan.report["findings_truncated"])
        with self.assertRaisesRegex(PlaylistError, "entry_limit"):
            self.plan(max_entries=10)
        for options in [dict(max_bytes=0), dict(max_findings=-1), dict(max_entries=True)]:
            with self.assertRaisesRegex(PlaylistError, "invalid_limits"):
                self.plan(**options)

    def test_json_duplicate_keys_and_invalid_json(self):
        for raw, code in [
            (' {"version":1,"version":2}', "duplicate_json_key"),
            ("[unclosed", "invalid_json"),
        ]:
            self.mapping.write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(PlaylistError, code):
                plan_relocation(self.source, self.mapping, self.output)

    def test_config_validation(self):
        variants = [
            {},
            {"version": True},
            {"source_style": []},
            {"unknown": 1},
            {"mappings": []},
            {"mappings": [{"from": "M:\\Music"}]},
            {"mappings": [{"from": "M:\\Music", "to": 1}]},
            {"mappings": [{"from": "relative", "to": "library"}]},
            {"mappings": [{"from": "M:\\Music", "to": "absent"}]},
            {"mappings": [{"from": "M:\\Music", "to": "old.m3u8"}]},
        ]
        original = self.config.copy()
        for update in variants:
            self.config = {**original, **update} if update else {}
            with self.subTest(update=update), self.assertRaises(PlaylistError):
                self.plan()

    def test_duplicate_prefix_map_rejected(self):
        self.config["mappings"].append({"from": "m:/music", "to": "library"})
        with self.assertRaisesRegex(PlaylistError, "duplicate_mapping_source"):
            self.plan()

    def test_invalid_base_and_missing_output_parent(self):
        self.config["source_base"] = "relative"
        with self.assertRaises(PlaylistError):
            self.plan()
        self.output = self.root / "absent" / "new.m3u8"
        with self.assertRaisesRegex(PlaylistError, "output_parent_missing"):
            self.plan()

    def test_report_does_not_include_titles_or_paths(self):
        receipt = json.dumps(self.plan().report)
        for private in ["Private title", "Tone.wav", str(self.root)]:
            self.assertNotIn(private, receipt)

    def test_cli_exit_codes_and_no_write_when_blocked(self):
        args = [str(self.source), "--map", str(self.mapping), "--output", str(self.output)]
        run = subprocess.run(
            [sys.executable, "-m", "playlist_relocate", *args, "--json"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["status"], "ready")
        self.assertFalse(self.output.exists())
        self.source.write_text("M:\\Music\\missing.wav\n", encoding="utf-8")
        run = subprocess.run(
            [sys.executable, "-m", "playlist_relocate", *args, "--write", "--json"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertFalse(self.output.exists())
        self.mapping.write_text("bad", encoding="utf-8")
        run = subprocess.run(
            [sys.executable, "-m", "playlist_relocate", *args, "--json"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(run.returncode, 2)
        self.assertNotIn("Traceback", run.stderr)

    def test_cli_text_and_write(self):
        args = [str(self.source), "--map", str(self.mapping), "--output", str(self.output)]
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(main([*args, "--write"]), 0)
        self.assertIn("WRITTEN", stream.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(main(args), 2)
        self.assertIn("ERROR", stream.getvalue())

    def test_broken_output_symlink_not_followed(self):
        destination = self.root / "do-not-create.m3u8"
        try:
            self.output.symlink_to(destination)
        except OSError:
            self.skipTest("Symlink creation not available to this OS user")
        with self.assertRaisesRegex(PlaylistError, "output_exists"):
            self.plan()
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
