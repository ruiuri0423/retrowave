# -*- coding: utf-8 -*-
"""RetroWave - 數位電路波型繪製工具

純標準庫 tkinter 的數位時序/波形編輯器（PNG 匯出需 Pillow）。
套件分層（設計文件 §14）：邏輯單元 (model/templates) 與繪圖單元
(elements/engine/backends/export) 完全 headless；只有 app 模組 import tkinter。
"""
__version__ = "1.25"

from .backends import PILCanvas, SVGCanvas
from .document import Document
from .elements import WAVE_TYPES
from .engine import Engine
from .geometry import Geometry
from .model import DEFAULT_PERIODS, Model, Row
from .templates import TemplateLibrary
from .theme import Style

_UI_NAMES = ("App", "make_key_button", "SHIFT_MASK", "CTRL_MASK")


def __getattr__(name):              # PEP 562：UI 延遲載入，核心匯入不碰 tkinter
    if name in _UI_NAMES:
        from . import app
        return getattr(app, name)
    raise AttributeError(f"module 'retrowave' has no attribute {name!r}")
