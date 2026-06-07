# -*- coding: utf-8 -*-
"""v1.27 開啟教學測試：設定持久化、遮罩流程（下一步/上一步/完成勾選/略過）、
App 整合（環境變數抑制、Help 強制重開）。"""
import pytest

import retrowave.tutorial as tut
from retrowave.tutorial import TutorialOverlay


@pytest.fixture
def settings_tmp(tmp_path, monkeypatch):
    """把設定檔導到暫存目錄，避免動到真實 ~/.retrowave。"""
    monkeypatch.setattr(tut, "SETTINGS_DIR", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------- 設定持久化
def test_tutorial_enabled_defaults_true(settings_tmp):
    assert tut.tutorial_enabled() is True


def test_set_tutorial_enabled_roundtrip(settings_tmp):
    tut.set_tutorial_enabled(False)
    assert tut.tutorial_enabled() is False
    assert (settings_tmp / "settings.json").exists()
    tut.set_tutorial_enabled(True)
    assert tut.tutorial_enabled() is True


def test_settings_preserve_other_keys(settings_tmp):
    tut.save_settings({"other": 123})
    tut.set_tutorial_enabled(False)
    d = tut.load_settings()
    assert d["other"] == 123 and d["show_tutorial"] is False


# ---------------------------------------------------------------- 遮罩流程
def _open_overlay(app):
    ov = TutorialOverlay(app, app._tutorial_steps())
    app.update_idletasks()
    return ov


def test_overlay_steps_and_finish_dont_show(app, settings_tmp):
    ov = _open_overlay(app)
    n = len(ov.steps)
    assert n >= 4 and ov.idx == 0
    for _ in range(n - 1):
        ov.next()
    assert ov.idx == n - 1
    ov.next()                                     # 最後一步再按下一步不越界
    assert ov.idx == n - 1
    ov.prev()
    assert ov.idx == n - 2
    ov.next()
    assert ov.dont_show.get() is True             # 預設勾選
    ov.finish()
    assert not ov.winfo_exists()
    assert tut.tutorial_enabled() is False        # 勾選不顯示 → 永久關閉


def test_overlay_finish_unchecked_keeps_enabled(app, settings_tmp):
    ov = _open_overlay(app)
    ov.idx = len(ov.steps) - 1
    ov.dont_show.set(False)
    ov.finish()
    assert tut.tutorial_enabled() is True         # 未勾選 → 下次仍顯示


def test_overlay_skip_disables_permanently(app, settings_tmp):
    ov = _open_overlay(app)
    ov.skip()                                     # 第一步直接略過
    assert not ov.winfo_exists()
    assert tut.tutorial_enabled() is False


def test_overlay_highlights_have_targets(app, settings_tmp):
    """步驟目標必須是存在的 widget（首尾兩步為全畫面 None）。"""
    steps = app._tutorial_steps()
    assert steps[0][0] is None and steps[-1][0] is None
    for target, title, body in steps[1:-1]:
        assert target is not None and target.winfo_exists()
        assert title and body
    ov = _open_overlay(app)
    ov.idx = 1; ov._show_step()                   # 有目標的步驟畫得出 bbox
    assert ov._target_bbox(steps[1][0]) is not None
    ov.close()


# ---------------------------------------------------------------- App 整合
def test_app_respects_env_suppression(app, settings_tmp):
    app._maybe_show_tutorial()                    # conftest 已設 RETROWAVE_NO_TUTORIAL
    assert getattr(app, "_tutorial", None) is None or not app._tutorial.winfo_exists()


def test_app_force_reopen_via_help(app, settings_tmp):
    tut.set_tutorial_enabled(False)               # 即使使用者已關閉
    app._maybe_show_tutorial(force=True)          # Help 選單仍可重開
    assert app._tutorial.winfo_exists()
    app._tutorial.skip()
