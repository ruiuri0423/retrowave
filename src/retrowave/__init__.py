# -*- coding: utf-8 -*-
"""RetroWave - digital circuit waveform drawing tool

A pure standard-library tkinter digital timing/waveform editor (PNG export needs Pillow).
Package layering (design spec §14): logic units (model/templates) and drawing units
(elements/engine/backends/export) are fully headless; only the app module imports tkinter.
"""
__version__ = "1.29"

from .backends import PILCanvas, SVGCanvas
from .document import Document
from .elements import WAVE_TYPES
from .engine import Engine
from .geometry import Geometry
from .model import DEFAULT_PERIODS, Model, Row
from .templates import TemplateLibrary
from .theme import Style

_UI_NAMES = ("App", "make_key_button", "SHIFT_MASK", "CTRL_MASK")


def __getattr__(name):              # PEP 562: lazy UI loading, core imports never touch tkinter
    if name in _UI_NAMES:
        from . import app
        return getattr(app, name)
    raise AttributeError(f"module 'retrowave' has no attribute {name!r}")
