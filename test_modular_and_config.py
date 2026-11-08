# -*- coding: utf-8 -*-
import unittest
import tempfile
import shutil
from pathlib import Path
import configparser

from config import Config, get_app_dir
from tagger import parse_csv_metadata, find_cover_image
from ui.tab_archive import CSV_TEMPLATE, build_archive_tab
from ui.tab_rip import build_rip_tab
import flet as ft


class TestConfigAutoDefaults(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_path = self.temp_dir / "config.ini"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_first_run_generates_config_when_missing(self):
        """When config.ini does not exist, it should be created with clean default paths."""
        self.assertFalse(self.config_path.exists())
        cfg = Config(config_path=self.config_path)
        self.assertTrue(self.config_path.exists())

        app_dir = get_app_dir()
        self.assertEqual(cfg.temp_dir, app_dir / "temp")
        self.assertEqual(cfg.unprocessed_dir, app_dir / "temp_unprocessed")
        self.assertEqual(cfg.output_dir, app_dir / "output")
        self.assertEqual(cfg.drive_letter, "D:")

    def test_empty_paths_in_existing_config_resolve_dynamically(self):
        """If config.ini has empty paths, properties resolve dynamically to app_dir defaults."""
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("[PATHS]\ntemp_dir =\nunprocessed_dir =\noutput_dir =\n")

        cfg = Config(config_path=self.config_path)
        app_dir = get_app_dir()
        self.assertEqual(cfg.temp_dir, app_dir / "temp")
        self.assertEqual(cfg.unprocessed_dir, app_dir / "temp_unprocessed")
        self.assertEqual(cfg.output_dir, app_dir / "output")

    def test_explicit_custom_paths_preserved(self):
        """Custom configured paths should be respected."""
        custom_out = self.temp_dir / "my_music"
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(f"[PATHS]\noutput_dir = {custom_out}\n")

        cfg = Config(config_path=self.config_path)
        self.assertEqual(cfg.output_dir, custom_out)


class TestCoverSearchStrictIsolation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.album_dir = self.temp_dir / "album_01"
        self.album_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_no_fallback_to_parent_dir(self):
        """A cover in the parent dir should NOT be picked up if album dir has none."""
        parent_cover = self.temp_dir / "cover.jpg"
        parent_cover.write_bytes(b"dummy")

        found = find_cover_image(self.album_dir)
        self.assertIsNone(found)

    def test_finds_cover_in_own_album_dir(self):
        """A cover within the album dir should be detected."""
        album_cover = self.album_dir / "cover.jpg"
        album_cover.write_bytes(b"dummy")

        found = find_cover_image(self.album_dir)
        self.assertIsNotNone(found)
        self.assertEqual(found, album_cover)


class TestModularTabsIndependentConstruction(unittest.TestCase):
    def setUp(self):
        class MockPage:
            def __init__(self):
                self.title = ""
                self.window = type("MockWindow", (), {"width": 0, "height": 0, "min_width": 0, "min_height": 0})()
                self.padding = 0
                self.theme = None
                self.dark_theme = None
                self.theme_mode = None
                self.services = []
                self.overlay = []
                self.appbar = None
                self.controls = []

            def add(self, control):
                self.controls.append(control)

            def update(self):
                pass

            def run_task(self, coro, fn=None):
                pass

        self.page = MockPage()
        self.file_picker = ft.FilePicker()

    def test_build_rip_tab_standalone(self):
        tab1_view, initial_check = build_rip_tab(
            page=self.page,
            file_picker=self.file_picker,
            show_notification=lambda msg, err=False: None,
            post_ui=lambda fn: fn(),
        )
        self.assertIsInstance(tab1_view, ft.Container)
        self.assertTrue(callable(initial_check))

    def test_build_archive_tab_standalone(self):
        tab2_view, refresh_pending, on_key = build_archive_tab(
            page=self.page,
            file_picker=self.file_picker,
            show_notification=lambda msg, err=False: None,
            post_ui=lambda fn: fn(),
        )
        self.assertIsInstance(tab2_view, ft.Container)
        self.assertTrue(callable(refresh_pending))
        self.assertTrue(callable(on_key))

    def test_in_memory_csv_template_parses(self):
        tracks = parse_csv_metadata(CSV_TEMPLATE)
        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[0]["track"], "01")
        self.assertEqual(tracks[0]["title"], "Track 01")
        self.assertEqual(tracks[1]["track"], "02")


if __name__ == "__main__":
    unittest.main()
