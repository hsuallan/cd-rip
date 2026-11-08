import os
import sys
import configparser
from pathlib import Path


def get_app_dir() -> Path:
    """Return application root directory (executable folder if frozen, script folder if running from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_FILE = get_app_dir() / "config.ini"


class Config:
    def __init__(self, config_path=None):
        self.config_path = Path(config_path) if config_path else CONFIG_FILE
        self.parser = configparser.ConfigParser()
        self.load()

    def _get_default_paths(self) -> dict[str, str]:
        app_dir = get_app_dir()
        return {
            "temp_dir": str(app_dir / "temp"),
            "unprocessed_dir": str(app_dir / "temp_unprocessed"),
            "output_dir": str(app_dir / "output"),
            "foobar_path": r"C:\Program Files\foobar2000\foobar2000.exe",
            "ripper_exe": "",
        }

    def _create_default_config(self):
        defaults = self._get_default_paths()
        self.parser["PATHS"] = defaults
        self.parser["CD"] = {
            "drive_letter": "D:",
            "flac_compression_level": "8",
            "eject_after_rip": "true",
        }
        self.parser["TAGGING"] = {
            "folder_format": "{album}",
            "filename_format": "{track}. {title}.flac",
            "cover_names": "cover, photo, folder, front",
            "write_genere_tag": "true",
        }
        self.parser["BEHAVIOR"] = {
            "move_temp_files": "true",
            "open_in_foobar": "true",
            "fallback_open_explorer": "true",
        }
        self.parser["UI"] = {
            "language": "",
        }
        self.save()

    def load(self):
        if not self.config_path.exists():
            self._create_default_config()
            return

        self.parser.read(self.config_path, encoding="utf-8")
        needs_save = False

        # Ensure all required sections exist
        for sec in ["PATHS", "CD", "TAGGING", "BEHAVIOR", "UI"]:
            if not self.parser.has_section(sec):
                self.parser.add_section(sec)
                needs_save = True

        if needs_save:
            self.save()

    # [PATHS]
    @property
    def temp_dir(self) -> Path:
        val = self.parser.get("PATHS", "temp_dir", fallback="").strip()
        if not val:
            val = str(get_app_dir() / "temp")
        return Path(val)

    @property
    def unprocessed_dir(self) -> Path:
        val = self.parser.get("PATHS", "unprocessed_dir", fallback="").strip()
        if not val:
            val = str(get_app_dir() / "temp_unprocessed")
        return Path(val)

    @property
    def output_dir(self) -> Path:
        val = self.parser.get("PATHS", "output_dir", fallback="").strip()
        if not val:
            val = str(get_app_dir() / "output")
        return Path(val)

    @property
    def foobar_path(self) -> str:
        return self.parser.get("PATHS", "foobar_path", fallback=r"C:\Program Files\foobar2000\foobar2000.exe")

    @property
    def ripper_exe(self) -> str:
        return self.parser.get("PATHS", "ripper_exe", fallback="")

    # [CD]
    @property
    def drive_letter(self) -> str:
        return self.parser.get("CD", "drive_letter", fallback="D:")

    @property
    def flac_compression_level(self) -> int:
        return self.parser.getint("CD", "flac_compression_level", fallback=8)

    @property
    def eject_after_rip(self) -> bool:
        return self.parser.getboolean("CD", "eject_after_rip", fallback=True)

    # [TAGGING]
    @property
    def folder_format(self) -> str:
        return self.parser.get("TAGGING", "folder_format", fallback="{album}")

    @property
    def filename_format(self) -> str:
        return self.parser.get("TAGGING", "filename_format", fallback="{track}. {title}.flac")

    @property
    def cover_names(self) -> list[str]:
        raw = self.parser.get("TAGGING", "cover_names", fallback="cover, photo, folder, front")
        return [item.strip() for item in raw.split(",") if item.strip()]

    @property
    def write_genere_tag(self) -> bool:
        return self.parser.getboolean("TAGGING", "write_genere_tag", fallback=True)

    # [BEHAVIOR]
    @property
    def move_temp_files(self) -> bool:
        return self.parser.getboolean("BEHAVIOR", "move_temp_files", fallback=True)

    @property
    def open_in_foobar(self) -> bool:
        return self.parser.getboolean("BEHAVIOR", "open_in_foobar", fallback=True)

    @property
    def fallback_open_explorer(self) -> bool:
        return self.parser.getboolean("BEHAVIOR", "fallback_open_explorer", fallback=True)

    # [UI]
    @property
    def language(self) -> str:
        return self.parser.get("UI", "language", fallback="").strip()

    def set_language(self, lang: str):
        self.set_value("UI", "language", lang)
        self.save()

    def set_value(self, section: str, key: str, value: str):
        if not self.parser.has_section(section):
            self.parser.add_section(section)
        self.parser.set(section, key, str(value))

    def save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            self.parser.write(f)


# Singleton instance for quick importing
cfg = Config()
