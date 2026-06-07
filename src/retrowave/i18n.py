# -*- coding: utf-8 -*-
"""Tiny i18n layer (headless).

Design (spec §11.2):
- **English source strings are the catalog keys.** UI code wraps every
  user-facing string with ``tr("...")``; for the default language ("en") the
  string is returned unchanged, so English needs no catalog at all and an
  untranslated string gracefully falls back to English.
- Catalogs are plain Python dicts in ``retrowave.locales`` (bundled as normal
  modules — no data files, so PyInstaller onefile needs no extra flags).
- The preference persists as the ``language`` key in usersettings and is
  applied once at startup; switching languages takes effect after restart
  (no live re-render of already-built widgets).
"""
from .locales import zh_tw

DEFAULT = "en"
_CATALOGS = {"zh-TW": zh_tw.TRANSLATIONS}
_lang = DEFAULT


def available_languages():
    """code -> native display name (shown in the Language menu)."""
    return {"en": "English", "zh-TW": "繁體中文"}


def set_language(code):
    """Switch the active language; unknown codes fall back to English."""
    global _lang
    _lang = code if code in available_languages() else DEFAULT
    return _lang


def get_language():
    return _lang


def tr(text):
    """Translate a source (English) string; falls back to the string itself."""
    if _lang == DEFAULT:
        return text
    return _CATALOGS.get(_lang, {}).get(text, text)
