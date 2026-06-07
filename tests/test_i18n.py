# -*- coding: utf-8 -*-
"""i18n layer tests: English-keys-as-source design, fallback semantics,
language persistence, and catalog sanity."""
import pytest

import retrowave.i18n as i18n
from retrowave.i18n import available_languages, get_language, set_language, tr
from retrowave.locales import zh_tw


@pytest.fixture(autouse=True)
def reset_language():
    """i18n keeps module-level state; always restore English after each test."""
    yield
    set_language("en")


def test_default_is_english_passthrough():
    assert get_language() == "en"
    assert tr("Anything at all") == "Anything at all"


def test_switch_to_zh_tw_translates_known_keys():
    set_language("zh-TW")
    assert tr("Language") == "語言"
    assert tr("Interactive tutorial") == "互動教學"


def test_unknown_string_falls_back_to_english():
    set_language("zh-TW")
    assert tr("No such catalog entry __x__") == "No such catalog entry __x__"


def test_invalid_language_falls_back_to_default():
    assert set_language("fr") == "en"
    assert get_language() == "en"


def test_available_languages_shape():
    langs = available_languages()
    assert langs["en"] == "English" and "zh-TW" in langs


def test_catalog_keys_are_english_sources():
    """Keys must be the English source strings (no Chinese keys), values non-empty."""
    import re
    for k, v in zh_tw.TRANSLATIONS.items():
        assert not re.search(r"[一-鿿]", k), f"catalog key must be English source: {k!r}"
        assert isinstance(v, str) and v, f"empty translation for {k!r}"


def test_language_preference_persists(tmp_path, monkeypatch):
    import retrowave.usersettings as us
    monkeypatch.setattr(us, "SETTINGS_DIR", str(tmp_path))
    us.set_value("language", "zh-TW")
    assert us.get_value("language") == "zh-TW"
