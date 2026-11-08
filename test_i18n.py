# -*- coding: utf-8 -*-
"""
Unit tests for the i18n internationalization module, locale catalogs,
OS language detection, config persistence, and reactive retranslation.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config, get_app_dir, cfg
import i18n
from i18n import (
    t,
    get_locale,
    set_locale,
    get_available_locales,
    detect_system_language,
    subscribe,
    unsubscribe,
    clear_subscribers,
    init_locale,
    I18nManager,
    DEFAULT_LOCALE,
)


class TestI18nCatalogs(unittest.TestCase):
    """Verifies all locale JSON resource files are well-formed and complete."""

    def setUp(self):
        self.locales_dir = Path(__file__).resolve().parent / "locales"

    def test_expected_locale_files_exist(self):
        expected_locales = ["zh_TW.json", "zh_CN.json", "en.json", "ja.json"]
        for fname in expected_locales:
            fpath = self.locales_dir / fname
            self.assertTrue(fpath.is_file(), f"Missing expected locale file: {fname}")

    def test_locale_json_validity_and_meta(self):
        for json_path in self.locales_dir.glob("*.json"):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("_meta", data, f"{json_path.name} missing _meta section")
            self.assertIn("code", data["_meta"])
            self.assertIn("name", data["_meta"])
            self.assertEqual(data["_meta"]["code"], json_path.stem)

    def test_key_parity_across_locales(self):
        """Ensure all keys in zh_TW are translated in en, ja, and zh_CN."""
        def get_all_keys(d, prefix=""):
            keys = set()
            for k, v in d.items():
                if k == "_meta":
                    continue
                full_key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    keys.update(get_all_keys(v, full_key))
                else:
                    keys.add(full_key)
            return keys

        with open(self.locales_dir / "zh_TW.json", "r", encoding="utf-8") as f:
            zh_tw_keys = get_all_keys(json.load(f))

        for locale_code in ["en", "ja", "zh_CN"]:
            with open(self.locales_dir / f"{locale_code}.json", "r", encoding="utf-8") as f:
                loc_keys = get_all_keys(json.load(f))
            missing = zh_tw_keys - loc_keys
            self.assertEqual(
                missing,
                set(),
                f"Locale {locale_code} is missing keys: {missing}",
            )


class TestI18nTranslations(unittest.TestCase):
    """Verifies translation lookup, interpolation, and fallbacks."""

    def setUp(self):
        self.orig_locale = get_locale()

    def tearDown(self):
        set_locale(self.orig_locale, notify=False)

    def test_basic_lookup_in_all_languages(self):
        expected = {
            "zh_TW": "連續轉檔模式",
            "en": "Continuous Rip Mode",
            "ja": "連続リッピングモード",
            "zh_CN": "连续转档模式",
        }
        for code, expected_text in expected.items():
            set_locale(code, notify=False)
            self.assertEqual(t("app.tab_rip"), expected_text)

    def test_parameter_interpolation(self):
        set_locale("zh_TW", notify=False)
        res_zh = t("rip.disc_progress", current=3, total=10, percent=30.0)
        self.assertIn("3/10", res_zh)
        self.assertIn("30.0%", res_zh)

        set_locale("en", notify=False)
        res_en = t("rip.disc_progress", current=3, total=10, percent=30.0)
        self.assertIn("3/10", res_en)
        self.assertIn("30.0%", res_en)

    def test_fallback_to_default_locale(self):
        manager = I18nManager()
        manager.translations["custom"] = {"app": {"only_in_custom": "Hello"}}
        manager.set_locale("custom", notify=False)

        # Key present in custom
        self.assertEqual(manager.translate("app.only_in_custom"), "Hello")
        # Key missing in custom, should fall back to DEFAULT_LOCALE (zh_TW)
        self.assertEqual(manager.translate("app.tab_rip"), "連續轉檔模式")
        # Completely unknown key falls back to key name itself
        self.assertEqual(manager.translate("non.existent.key"), "non.existent.key")


class TestOSLanguageDetection(unittest.TestCase):
    """Verifies automatic detection of system UI language across different platforms and settings."""

    @patch("ctypes.windll.kernel32.GetUserDefaultUILanguage", create=True)
    def test_windows_api_detection(self, mock_get_lang):
        mock_get_lang.return_value = 0x0411  # Japanese
        detected = detect_system_language(["zh_TW", "en", "ja"])
        self.assertEqual(detected, "ja")

        mock_get_lang.return_value = 0x0409  # English (US)
        detected = detect_system_language(["zh_TW", "en", "ja"])
        self.assertEqual(detected, "en")

        mock_get_lang.return_value = 0x0404  # Traditional Chinese (Taiwan)
        detected = detect_system_language(["zh_TW", "en", "ja"])
        self.assertEqual(detected, "zh_TW")

        mock_get_lang.return_value = 0x0804  # Simplified Chinese (PRC)
        detected = detect_system_language(["zh_TW", "zh_CN", "en", "ja"])
        self.assertEqual(detected, "zh_CN")

    @patch("ctypes.windll", create=True, new=None)
    @patch("locale.getlocale")
    def test_locale_module_fallback(self, mock_getlocale):
        mock_getlocale.return_value = ("Japanese_Japan", "932")
        detected = detect_system_language(["zh_TW", "en", "ja"])
        self.assertEqual(detected, "ja")

        mock_getlocale.return_value = ("Chinese (Traditional)_Taiwan", "950")
        detected = detect_system_language(["zh_TW", "en", "ja"])
        self.assertEqual(detected, "zh_TW")

    @patch("ctypes.windll", create=True, new=None)
    @patch("locale.getlocale", return_value=(None, None))
    def test_env_var_fallback(self, mock_getlocale):
        with patch.dict(os.environ, {"LANG": "en_US.UTF-8"}):
            detected = detect_system_language(["zh_TW", "en", "ja"])
            self.assertEqual(detected, "en")

    @patch("ctypes.windll", create=True, new=None)
    @patch("locale.getlocale", return_value=(None, None))
    def test_unknown_locale_defaults_gracefully(self, mock_getlocale):
        with patch.dict(os.environ, {"LANG": "xyz_UNKNOWN"}):
            detected = detect_system_language(["zh_TW", "en", "ja"])
            self.assertEqual(detected, DEFAULT_LOCALE)

    @patch("ctypes.windll", create=True, new=None)
    @patch("locale.getlocale", return_value=(None, None))
    def test_extensible_custom_locale_detection(self, mock_getlocale):
        """Verifies that newly added languages (e.g. de, fr, ko) are auto-detected by prefix without code changes."""
        with patch.dict(os.environ, {"LANG": "de_DE.UTF-8"}):
            detected = detect_system_language(["zh_TW", "en", "ja", "de"])
            self.assertEqual(detected, "de")

        with patch.dict(os.environ, {"LANG": "fr_FR.UTF-8"}):
            detected = detect_system_language(["zh_TW", "en", "ja", "fr"])
            self.assertEqual(detected, "fr")



class TestConfigLanguagePersistence(unittest.TestCase):
    """Verifies saving and loading language settings in config.ini."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_path = self.temp_dir / "config.ini"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_config_has_empty_language(self):
        cfg = Config(config_path=self.config_path)
        self.assertEqual(cfg.language, "")

    def test_set_language_persists_to_file(self):
        cfg = Config(config_path=self.config_path)
        cfg.set_language("ja")

        # Reload from disk
        cfg2 = Config(config_path=self.config_path)
        self.assertEqual(cfg2.language, "ja")

        cfg2.set_language("en")
        cfg3 = Config(config_path=self.config_path)
        self.assertEqual(cfg3.language, "en")


class TestSubscriberPattern(unittest.TestCase):
    """Verifies that reactive subscriber callbacks are notified when locale changes."""

    def test_subscription_callback_invoked(self):
        manager = I18nManager()
        called_count = 0

        def on_change():
            nonlocal called_count
            called_count += 1

        manager.subscribe(on_change)
        manager.set_locale("en")
        self.assertEqual(called_count, 1)

        manager.set_locale("ja")
        self.assertEqual(called_count, 2)

        manager.unsubscribe(on_change)
        manager.set_locale("zh_TW")
        self.assertEqual(called_count, 2)

    def test_clear_subscribers(self):
        manager = I18nManager()
        called_count = 0
        manager.subscribe(lambda: None)
        manager.subscribe(lambda: None)
        self.assertEqual(len(manager.subscribers), 2)
        manager.clear_subscribers()
        self.assertEqual(len(manager.subscribers), 0)



class TestAppUIRetranslationIntegration(unittest.TestCase):
    """Verifies that switching the language dropdown in the UI retranslates all page and tab controls."""

    def setUp(self):
        self.orig_locale = get_locale()
        self.orig_cfg_lang = cfg.language
        cfg.set_language("zh_TW")

    def tearDown(self):
        clear_subscribers()
        set_locale(self.orig_locale, notify=False)
        cfg.set_language(self.orig_cfg_lang)

    def _create_mock_page(self):
        import flet as ft
        class MockPage:
            def __init__(self):
                self.title = ""
                self.window = type("MockWindow", (), {"width": 0, "height": 0, "min_width": 0, "min_height": 0})()
                self.padding = 0
                self.theme = None
                self.dark_theme = None
                self.theme_mode = ft.ThemeMode.LIGHT
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

        return MockPage()

    def test_ui_dynamic_retranslation_across_languages(self):
        import flet as ft
        from ui_app import create_app

        page = self._create_mock_page()
        app_main = create_app()

        # Start with Traditional Chinese
        set_locale("zh_TW", notify=False)
        app_main(page)

        self.assertEqual(page.title, "CD-RIP 數位化與 Tag 自動化歸檔系統")
        self.assertIsNotNone(page.appbar)

        # Find lang dropdown in appbar
        lang_dd = None
        for action in page.appbar.actions:
            if isinstance(action, ft.Dropdown):
                lang_dd = action
                break
        self.assertIsNotNone(lang_dd)
        self.assertEqual(lang_dd.value, "zh_TW")
        self.assertGreaterEqual(lang_dd.width, 180, "Dropdown width must be >= 180 to avoid cutting off language names like 'English'")
        self.assertIsNotNone(lang_dd.on_select, "Dropdown must register on_select handler for Flet 1.1+")

        # Simulate user switching to English via on_select event
        class DummySelectEvent:
            def __init__(self, ctrl, data):
                self.control = ctrl
                self.data = data

        lang_dd.value = "en"
        lang_dd.on_select(DummySelectEvent(lang_dd, "en"))

        self.assertEqual(page.title, "CD-RIP Digitization & Automated Tag Archiving System")
        tabs = page.controls[0]
        tab1_header = tabs.content.controls[0].tabs[0]
        tab2_header = tabs.content.controls[0].tabs[1]
        self.assertEqual(tab1_header.label, "Continuous Rip Mode")
        self.assertEqual(tab2_header.label, "Batch Archiving Mode")

        # Simulate user switching to Japanese via on_change for backwards compatibility
        lang_dd.value = "ja"
        lang_dd.on_change(None)

        self.assertEqual(page.title, "CD-RIP デジタル化＆自動タグ・アーカイブシステム")
        self.assertEqual(tab1_header.label, "連続リッピングモード")
        self.assertEqual(tab2_header.label, "一括アーカイブモード")

    @patch("ctypes.windll.kernel32.GetUserDefaultUILanguage", create=True)
    def test_boot_with_os_detected_language_when_config_empty(self, mock_get_lang):
        """Verifies that on first launch (empty config), app automatically boots into the OS language."""
        import flet as ft
        from ui_app import create_app

        cfg.set_language("")

        # 1. Test Japanese OS
        mock_get_lang.return_value = 0x0411  # Japanese
        page_ja = self._create_mock_page()
        app_main = create_app()
        app_main(page_ja)

        self.assertEqual(page_ja.title, "CD-RIP デジタル化＆自動タグ・アーカイブシステム")
        lang_dd_ja = next(c for c in page_ja.appbar.actions if isinstance(c, ft.Dropdown))
        self.assertEqual(lang_dd_ja.value, "ja")
        clear_subscribers()

        # 2. Test English OS
        mock_get_lang.return_value = 0x0409  # English (US)
        page_en = self._create_mock_page()
        app_main(page_en)

        self.assertEqual(page_en.title, "CD-RIP Digitization & Automated Tag Archiving System")
        lang_dd_en = next(c for c in page_en.appbar.actions if isinstance(c, ft.Dropdown))
        self.assertEqual(lang_dd_en.value, "en")

    def test_tab_granular_retranslation_state_preservation(self):
        """Verifies that granular states (hint text, prompt state, prep state, result card) retranslate cleanly."""
        import flet as ft
        from ui.tab_rip import build_rip_tab
        from ui.tab_archive import build_archive_tab

        page = self._create_mock_page()
        picker = ft.FilePicker()

        set_locale("zh_TW", notify=False)
        tab1_view, initial_check = build_rip_tab(
            page=page,
            file_picker=picker,
            show_notification=lambda *a, **k: None,
            post_ui=lambda fn: fn(),
        )
        tab2_view, refresh_pending, _ = build_archive_tab(
            page=page,
            file_picker=picker,
            show_notification=lambda *a, **k: None,
            post_ui=lambda fn: fn(),
        )

        # Initial check with no disc sets prompt state
        initial_check()

        # Switch to English
        set_locale("en")
        # In Tab 1: check retranslation of prompt
        tab1_col = tab1_view.content.controls[1].content.content
        disc_info = tab1_col.controls[0].controls[1]
        self.assertIn("No disc inserted", disc_info.value)

        # Switch to Japanese
        set_locale("ja")
        self.assertIn("ディスクが未挿入です", disc_info.value)


if __name__ == "__main__":
    unittest.main()
