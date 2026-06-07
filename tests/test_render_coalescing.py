# -*- coding: utf-8 -*-
"""v1.21 render 合併：request_render() 在同一事件迴圈周期內去重，
同步 render() 取消擱置請求，且最終畫面/狀態列與同步版本一致。"""
import pytest

from conftest import Ev, cell_xy, assert_invariants


@pytest.fixture
def draw_count(app, monkeypatch):
    """計數 Engine.draw 實際執行次數（render 的核心工作）。"""
    calls = {"n": 0}
    orig = app.engine.draw

    def counted(*a, **kw):
        calls["n"] += 1
        return orig(*a, **kw)

    monkeypatch.setattr(app.engine, "draw", counted)
    return calls


def test_burst_requests_coalesce_to_one_draw(app, draw_count):
    for _ in range(10):
        app.request_render()
    assert draw_count["n"] == 0                 # idle 前不重繪
    app.update_idletasks()
    assert draw_count["n"] == 1                 # 10 次請求 -> 1 次重繪
    app.update_idletasks()
    assert draw_count["n"] == 1                 # 不殘留重複排程


def test_sync_render_cancels_pending_request(app, draw_count):
    app.request_render()
    app.render()                                # 同步重繪
    assert draw_count["n"] == 1
    app.update_idletasks()
    assert draw_count["n"] == 1                 # 擱置請求已被取消，不重畫第二次


def test_request_after_sync_render_still_works(app, draw_count):
    app.render()
    app.request_render()
    app.update_idletasks()
    assert draw_count["n"] == 2


def test_paint_drag_burst_single_redraw_correct_result(app, draw_count):
    """一次筆刷拖曳（press + 3 motion + release）合併為一次重繪，且格子全部畫上。"""
    app._set_tool("H")
    app.update_idletasks(); draw_count["n"] = 0
    x0, y0 = cell_xy(app, 2, 0)
    app.on_press(Ev(x0, y0))
    for p in (1, 2, 3):
        app.on_motion(Ev(*cell_xy(app, 2, p)))
    app.on_release(Ev(*cell_xy(app, 2, 3)))
    assert draw_count["n"] == 0
    app.update_idletasks()
    assert draw_count["n"] == 1
    assert [c["type"] for c in app.model.signals[2]["cells"][0:4]] == ["H"] * 4
    assert_invariants(app.model)


def test_deferred_render_updates_canvas_and_status(app):
    """延遲重繪最終要真的反映到畫布與狀態列（與同步版本等價）。"""
    app._enter_pan_mode()                       # 內部走 request_render
    app.update_idletasks()
    assert "拖曳模式" in app.status.cget("text")
    app._set_tool("BUS")
    app.update_idletasks()
    assert "BUS" in app.status.cget("text")
    assert len(app.wave_cv.find_all()) > 0      # 畫布有內容


def test_render_pending_flag_cleared_after_idle(app):
    app.request_render()
    assert app._render_job is not None
    app.update_idletasks()
    assert app._render_job is None
