# -*- coding: utf-8 -*-
import unittest
from pathlib import Path
import numpy as np
import soundfile as sf
import mutagen.flac

from config import cfg
from tagger import parse_csv_metadata, find_cover_image, process_and_tag_flacs


class TestCDRipTool(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("test_workspace")
        self.test_dir.mkdir(exist_ok=True)
        self.temp_album_dir = self.test_dir / "CD_01_3tracks"
        self.temp_album_dir.mkdir(exist_ok=True)
        self.output_dir = self.test_dir / "output"
        self.output_dir.mkdir(exist_ok=True)

        # Create 3 tiny test FLAC files
        sr = 44100
        duration = 0.2  # 0.2 seconds
        samples = int(sr * duration)
        dummy_audio = np.zeros((samples, 2), dtype=np.int16)

        for i in range(1, 4):
            flac_path = self.temp_album_dir / f"{i:02d}. CD Track {i:02d}.flac"
            sf.write(str(flac_path), dummy_audio, sr, subtype='PCM_16')

        # Sample CSV
        self.csv_text = """%track%,%title%,%genre%,%artist%,%year%,%album%,%albumartist%,%composer%,%lyricist%
01,Test Track One,J-Pop,Test Artist 1,2026,Test Album,Main Artist,Composer 1,Lyricist 1
02,Test Track Two,J-Pop,Test Artist 2,2026,Test Album,Main Artist,Composer 2,Lyricist 2
03,Test Track Three (Inst),Instrumental,,2026,Test Album,Main Artist,,
"""

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_csv_parser(self):
        tracks = parse_csv_metadata(self.csv_text)
        self.assertEqual(len(tracks), 3)
        self.assertEqual(tracks[0]['track'], '01')
        self.assertEqual(tracks[0]['title'], 'Test Track One')
        self.assertEqual(tracks[0]['artist'], 'Test Artist 1')
        self.assertEqual(tracks[0]['albumartist'], 'Main Artist')
        self.assertEqual(tracks[2]['artist'], '')  # Empty artist for inst

    def test_process_and_tag_flacs(self):
        dest_dir, files = process_and_tag_flacs(
            temp_dir=str(self.temp_album_dir),
            csv_file_or_text=self.csv_text,
            output_base_dir=str(self.output_dir),
            move_files=False
        )

        self.assertTrue(dest_dir.exists())
        self.assertEqual(len(files), 3)

        # Verify tags on first file
        audio = mutagen.flac.FLAC(files[0])
        self.assertEqual(audio['title'][0], 'Test Track One')
        self.assertEqual(audio['artist'][0], 'Test Artist 1')
        self.assertEqual(audio['albumartist'][0], 'Main Artist')
        self.assertEqual(audio['album'][0], 'Test Album')
        self.assertEqual(audio['tracknumber'][0], '01')
        self.assertEqual(audio['tracktotal'][0], '03')

    def test_cover_conversion(self):
        from PIL import Image
        from tagger import process_cover_to_jpg
        from ui_app import format_mm_ss

        # Test mm:ss formatting
        self.assertEqual(format_mm_ss(238.0), "03:58")
        self.assertEqual(format_mm_ss(65), "01:05")
        self.assertEqual(format_mm_ss(0), "00:00")

        # Test PNG with alpha to JPEG cover.jpg conversion
        png_path = self.test_dir / "transparent.png"
        img = Image.new("RGBA", (50, 50), (255, 0, 0, 128))
        img.save(png_path, "PNG")

        dest_jpg = self.test_dir / "cover.jpg"
        data, mime = process_cover_to_jpg(png_path, dest_jpg)

        self.assertTrue(dest_jpg.exists())
        self.assertEqual(mime, "image/jpeg")
        self.assertGreater(len(data), 100)

        with Image.open(dest_jpg) as out_img:
            self.assertEqual(out_img.format, "JPEG")
            self.assertEqual(out_img.mode, "RGB")

    def test_clear_cover_none(self):
        # Create a cover.jpg in temp directory
        from PIL import Image
        temp_cover = self.temp_album_dir / "cover.jpg"
        img = Image.new("RGB", (20, 20), (100, 100, 100))
        img.save(temp_cover, "JPEG")

        # Process with custom_cover_path="NONE"
        dest_dir, files = process_and_tag_flacs(
            temp_dir=str(self.temp_album_dir),
            csv_file_or_text=self.csv_text,
            output_base_dir=str(self.output_dir),
            move_files=False,
            custom_cover_path="NONE"
        )

        # Ensure cover.jpg was NOT created in destination and FLAC has no picture
        self.assertFalse((dest_dir / "cover.jpg").exists())
        audio = mutagen.flac.FLAC(files[0])
        self.assertEqual(len(audio.pictures), 0)


if __name__ == '__main__':
    unittest.main()
