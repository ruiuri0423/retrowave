# -*- coding: utf-8 -*-
"""User preferences persisted in ~/.retrowave/settings.json.

Headless module (no tkinter) shared by the tutorial (show_tutorial) and the
i18n layer (language). Failures are swallowed gracefully: a missing or broken
settings file simply yields defaults.
"""
import json
import os

SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".retrowave")
SETTINGS_FILE = "settings.json"


def _settings_path():
    return os.path.join(SETTINGS_DIR, SETTINGS_FILE)


def load_settings():
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(d):
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_value(key, default=None):
    return load_settings().get(key, default)


def set_value(key, value):
    d = load_settings()
    d[key] = value
    return save_settings(d)
