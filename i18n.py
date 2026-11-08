# -*- coding: utf-8 -*-
"""
Internationalization (i18n) module for CD-RIP Desktop Application.
Supports extensible JSON locale resources, OS system language detection,
subscriber pattern for reactive UI updates, and formatted key translation.
"""

import json
import locale
import os
import sys
from pathlib import Path
from typing import Callable, Any

DEFAULT_LOCALE = "zh_TW"


def get_locales_dir() -> Path:
    """Return directory where locale JSON files are stored."""
    # If running frozen via PyInstaller
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cand = Path(meipass) / "locales"
            if cand.is_dir():
                return cand
        exec_cand = Path(sys.executable).resolve().parent / "locales"
        if exec_cand.is_dir():
            return exec_cand

    # Source code directory
    base_dir = Path(__file__).resolve().parent / "locales"
    if base_dir.is_dir():
        return base_dir
    return Path("locales").resolve()


def detect_system_language(available_codes: list[str] = None) -> str:
    """
    Detect operating system UI language.
    Priority:
    1. Windows kernel32 GetUserDefaultUILanguage() mapped through locale.windows_locale
    2. Python locale.getlocale()
    3. Standard POSIX environment variables (LC_ALL, LC_MESSAGES, LANG, LANGUAGE)
    """
    if available_codes is None:
        available_codes = ["zh_TW", "zh_CN", "en", "ja"]

    candidates = []

    # 1. Windows API
    try:
        import ctypes
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "kernel32"):
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            win_loc = locale.windows_locale.get(lang_id)
            if win_loc:
                candidates.append(win_loc)
    except Exception:
        pass

    # 2. Python locale.getlocale()
    try:
        loc = locale.getlocale()[0]
        if loc:
            candidates.append(loc)
    except Exception:
        pass

    # 3. Environment variables
    for env in ["LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"]:
        val = os.environ.get(env)
        if val:
            candidates.append(val)

    # Normalize candidates and match against available codes
    for cand in candidates:
        c = cand.lower().replace("-", "_")
        if "zh_tw" in c or "zh_hk" in c or "zh_mo" in c or "taiwan" in c or "traditional" in c:
            if "zh_TW" in available_codes:
                return "zh_TW"
        if "zh_cn" in c or "zh_sg" in c or "china" in c or "simplified" in c:
            if "zh_CN" in available_codes:
                return "zh_CN"
        if c.startswith("zh") or "chinese" in c:
            if "zh_TW" in available_codes:
                return "zh_TW"
        if c.startswith("ja") or "japanese" in c:
            if "ja" in available_codes:
                return "ja"
        if c.startswith("en") or "english" in c:
            if "en" in available_codes:
                return "en"
        # Extensible match for any code in available_codes (e.g. "de", "fr", "es", "ko")
        for code in available_codes:
            code_lower = code.lower().replace("-", "_")
            base_lang = code_lower.split("_")[0]
            if c == code_lower or c.startswith(code_lower + "_") or c.startswith(code_lower + ".") or c.startswith(base_lang + "_") or c == base_lang:
                return code

    return DEFAULT_LOCALE if DEFAULT_LOCALE in available_codes else (available_codes[0] if available_codes else "en")


class I18nManager:
    """Manages loaded locales, active language, and subscriber callbacks for dynamic retranslation."""

    def __init__(self, locales_dir: Path = None):
        self.locales_dir = Path(locales_dir) if locales_dir else get_locales_dir()
        self.translations: dict[str, dict] = {}
        self.locale_names: dict[str, str] = {}
        self.subscribers: list[Callable[[], None]] = []
        self._current_locale: str = DEFAULT_LOCALE
        self.reload_locales()

    def reload_locales(self):
        """Scans locales directory and loads all *.json translation catalogs."""
        self.translations.clear()
        self.locale_names.clear()

        if self.locales_dir.exists() and self.locales_dir.is_dir():
            for json_path in sorted(self.locales_dir.glob("*.json")):
                code = json_path.stem
                try:
                    with open(json_path, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)
                    meta = data.get("_meta", {})
                    name = meta.get("name", code)
                    actual_code = meta.get("code", code)
                    self.translations[actual_code] = data
                    self.locale_names[actual_code] = name
                except Exception as ex:
                    print(f"[i18n Warning] Failed to load locale {json_path}: {ex}")

        # Fallback if no files could be read
        if not self.translations:
            self.translations[DEFAULT_LOCALE] = {}
            self.locale_names[DEFAULT_LOCALE] = "繁體中文"

    def get_available_locales(self) -> list[dict[str, str]]:
        """Returns list of available locales, e.g. [{'code': 'zh_TW', 'name': '繁體中文'}, ...]."""
        preferred_order = ["zh_TW", "zh_CN", "en", "ja"]
        result = []
        for code in preferred_order:
            if code in self.translations:
                result.append({"code": code, "name": self.locale_names.get(code, code)})
        for code in sorted(self.translations.keys()):
            if code not in preferred_order:
                result.append({"code": code, "name": self.locale_names.get(code, code)})
        return result

    @property
    def current_locale(self) -> str:
        return self._current_locale

    def set_locale(self, locale_code: str, notify: bool = True):
        """Changes active locale and notifies subscribers."""
        if locale_code in self.translations:
            self._current_locale = locale_code
        elif DEFAULT_LOCALE in self.translations:
            self._current_locale = DEFAULT_LOCALE
        elif self.translations:
            self._current_locale = next(iter(self.translations))

        if notify:
            for cb in list(self.subscribers):
                try:
                    cb()
                except Exception as ex:
                    print(f"[i18n] Error executing subscriber callback: {ex}")

    def subscribe(self, callback: Callable[[], None]):
        """Register a callback to be called whenever active language changes."""
        if callback not in self.subscribers:
            self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[], None]):
        """Unregister a callback."""
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    def clear_subscribers(self):
        """Unregister all callbacks."""
        self.subscribers.clear()

    def _lookup(self, catalog: dict, key: str) -> Any:
        """Looks up a key with dot notation (e.g. 'rip.table.track') or flat."""
        if key in catalog:
            return catalog[key]
        parts = key.split(".")
        curr = catalog
        for p in parts:
            if isinstance(curr, dict) and p in curr:
                curr = curr[p]
            else:
                return None
        return curr

    def translate(self, key: str, **kwargs) -> str:
        """Translate key to current locale, falling back to DEFAULT_LOCALE, then key name."""
        curr_catalog = self.translations.get(self._current_locale, {})
        text = self._lookup(curr_catalog, key)

        if text is None:
            fallback_catalog = self.translations.get(DEFAULT_LOCALE, {})
            text = self._lookup(fallback_catalog, key)

        if text is None:
            return key

        if not isinstance(text, str):
            return str(text)

        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def init_locale(self, preferred_code: str = None) -> str:
        """Initialize locale using preferred code (e.g. from config) or auto-detect from OS."""
        available_codes = [loc["code"] for loc in self.get_available_locales()]
        if preferred_code and preferred_code in available_codes:
            self.set_locale(preferred_code, notify=False)
            return self._current_locale

        detected = detect_system_language(available_codes)
        self.set_locale(detected, notify=False)
        return self._current_locale


# Singleton instance
_i18n = I18nManager()

# Global convenience functions
t = _i18n.translate
get_locale = lambda: _i18n.current_locale
set_locale = _i18n.set_locale
get_available_locales = _i18n.get_available_locales
subscribe = _i18n.subscribe
unsubscribe = _i18n.unsubscribe
clear_subscribers = _i18n.clear_subscribers
init_locale = _i18n.init_locale

