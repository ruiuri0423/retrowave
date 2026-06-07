# -*- coding: utf-8 -*-
"""v1.25 Undo/Redo UI 測試：經由真實 App 手勢驗證「一個手勢 = 一個 undo 步」與深度 5。"""
import retrowave
from conftest import Ev, cell_xy, assert_invariants


def _click(app, row, per):
    x, y = cell_xy(app, row, per)
    app.on_press(Ev(x, y)); app.on_release(Ev(x, y))


def test_brush_stroke_is_single_undo_step(app):
    app._set_tool("H")
    x0, y0 = cell_xy(app, 2, 0)
    app.on_press(Ev(x0, y0))
    for p in (1, 2, 3):
        app.on_motion(Ev(*cell_xy(app, 2, p)))
    app.on_release(Ev(*cell_xy(app, 2, 3)))          # 一次筆刷：4 格
    assert app.doc.history() == (1, 0)               # = 一步
    app.do_undo()
    cells = app.model.signals[2]["cells"]
    assert cells[0]["type"] == "L" and cells[2]["type"] == "BUS"   # 回到 demo 原狀
    assert app.doc.history() == (0, 1)
    app.do_redo()
    assert [c["type"] for c in app.model.signals[2]["cells"][0:4]] == ["H"] * 4
    assert_invariants(app.model)


def test_fill_selection_is_single_undo_step(app):
    x0, y0 = cell_xy(app, 0, 0); x1, y1 = cell_xy(app, 1, 3)
    app.on_press(Ev(x0, y0, state=retrowave.SHIFT_MASK))
    app.on_motion(Ev(x1, y1, state=retrowave.SHIFT_MASK))
    app.on_release(Ev(x1, y1, state=retrowave.SHIFT_MASK))
    app._set_tool("HiZ")                              # 填入 2x4 = 8 格
    assert app.doc.history() == (1, 0)
    app.do_undo()
    assert app.model.signals[0]["cells"][0]["type"] == "CLK"
    assert_invariants(app.model)


def test_paste_cells_with_auto_rows_single_step(app):
    app.cell_sel = (0, 2, 0, 3); app._copy_ctx = "cells"
    app.do_copy()
    app._hover = (2, 4)
    app.do_paste()                                    # 自動加 2 列 + 12 格
    assert len(app.model.signals) == 5
    assert app.doc.history() == (1, 0)                # 整個貼上 = 一步
    app.do_undo()
    assert len(app.model.signals) == 3
    assert_invariants(app.model)


def test_click_without_change_not_recorded(app):
    app._enter_pan_mode()                             # 拖曳模式點擊不畫
    _click(app, 2, 0)
    assert app.doc.history() == (0, 0)


def test_depth_5_via_ui(app):
    app._set_tool("H")
    for p in range(7):                                # 7 個獨立點擊手勢（DATA 列，各格皆有變更）
        _click(app, 2, p)
    assert app.doc.history() == (5, 0)                # 只留最近 5 步
    n = 0
    while app.doc.can_undo():
        app.do_undo(); n += 1
    assert n == 5
    cells = app.model.signals[2]["cells"]
    assert cells[0]["type"] == "H" and cells[1]["type"] == "H"     # 最早兩步被擠出，無法復原
    assert cells[2] == {"type": "BUS", "text": "A5"}               # 後五步已還原 demo 原狀
    assert_invariants(app.model)


def test_paint_on_unchanged_cell_not_recorded(app):
    app._set_tool("H")
    _click(app, 1, 0)                                 # RST_N 已是 H：無實質變更
    assert app.doc.history() == (0, 0)                # 空交易不入棧


def test_undo_after_delete_clamps_selection(app):
    app.sig_sel = {0, 1, 2}; app.selected = 2
    app.doc.remove_signals([1, 2])
    app.do_undo()
    assert len(app.model.signals) == 3
    assert 0 <= app.selected < 3 and app.sig_sel
    assert app.cell_sel is None
    assert_invariants(app.model)


def test_undo_with_empty_stack_safe(app):
    app.do_undo()                                     # 空棧：不炸、狀態列提示
    assert "沒有可復原" in app.status.cget("text")
    app.do_redo()
    assert "沒有可重做" in app.status.cget("text")
