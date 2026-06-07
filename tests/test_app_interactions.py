# -*- coding: utf-8 -*-
"""互動煙霧測試：真實 App + 模擬滑鼠/鍵盤事件（會短暫開啟視窗）。
涵蓋：畫格、筆刷鎖列、BUS 保留、框選+填入、拖曳模式平移、複製貼上、範本插入。"""
import json

import retrowave
from conftest import Ev, cell_xy, assert_invariants


# ---------------------------------------------------------------- 繪製
def test_click_paints_cell(app):
    app._set_tool("H")
    x, y = cell_xy(app, 2, 0)                       # DATA 列 T0（原為 L）
    app.on_press(Ev(x, y)); app.on_release(Ev(x, y))
    assert app.model.signals[2]["cells"][0]["type"] == "H"
    assert_invariants(app.model)


def test_drag_brush_locks_starting_row(app):
    app._set_tool("H")
    x0, y0 = cell_xy(app, 2, 1)
    x1, y1 = cell_xy(app, 0, 4)                     # 往上拖到別列、第 4 週期
    app.on_press(Ev(x0, y0))
    app.on_motion(Ev(x1, y1))
    app.on_release(Ev(x1, y1))
    cells = app.model.signals[2]["cells"]
    assert [c["type"] for c in cells[1:5]] == ["H"] * 4   # 只畫起始列
    assert app.model.signals[0]["cells"][4]["type"] == "CLK"  # 其他列不受影響
    assert_invariants(app.model)


def test_bus_brush_preserves_existing_bus(app):
    app._set_tool("BUS")
    x0, y0 = cell_xy(app, 2, 1)                     # DATA: T2/T3=A5, T4=0F
    x1, y1 = cell_xy(app, 2, 4)
    app.on_press(Ev(x0, y0))
    app.on_motion(Ev(x1, y1))
    app.on_release(Ev(x1, y1))
    cells = app.model.signals[2]["cells"]
    assert cells[1]["type"] == "BUS"                # 新畫的
    assert cells[2]["text"] == "A5" and cells[4]["text"] == "0F"  # 原 BUS 保留
    assert_invariants(app.model)


def test_pan_mode_click_never_paints(app):
    app._enter_pan_mode()
    assert app.active_tool is None
    x, y = cell_xy(app, 2, 0)
    app.on_press(Ev(x, y)); app.on_release(Ev(x, y))
    assert app.model.signals[2]["cells"][0]["type"] == "L"
    assert_invariants(app.model)


# ---------------------------------------------------------------- 框選 + 填入
def test_marquee_select_then_fill(app):
    x0, y0 = cell_xy(app, 1, 1)
    x1, y1 = cell_xy(app, 2, 3)
    app.on_press(Ev(x0, y0, state=retrowave.SHIFT_MASK))
    app.on_motion(Ev(x1, y1, state=retrowave.SHIFT_MASK))
    app.on_release(Ev(x1, y1, state=retrowave.SHIFT_MASK))
    assert app.cell_sel == (1, 2, 1, 3)
    app._set_tool("HiZ")                            # 有框選 -> 填入而非切工具
    for s in (1, 2):
        assert [c["type"] for c in app.model.signals[s]["cells"][1:4]] == ["HiZ"] * 3
    assert app.cell_sel is not None                 # 填入後選取保留
    assert_invariants(app.model)


def test_marquee_works_in_pan_mode(app):
    app._enter_pan_mode()
    x0, y0 = cell_xy(app, 0, 0)
    x1, y1 = cell_xy(app, 1, 2)
    app.on_press(Ev(x0, y0, state=retrowave.CTRL_MASK))
    app.on_motion(Ev(x1, y1, state=retrowave.CTRL_MASK))
    app.on_release(Ev(x1, y1, state=retrowave.CTRL_MASK))
    assert app.cell_sel == (0, 1, 0, 2)
    assert_invariants(app.model)


def test_escape_clears_selection_and_tool(app):
    app._set_tool("H")
    app.cell_sel = (0, 1, 0, 1)
    app._enter_pan_mode()
    assert app.cell_sel is None and app.active_tool is None


# ---------------------------------------------------------------- 拖曳模式平移
def test_pan_locked_when_content_fits(app):
    h_ok, v_ok = app._scrollable()
    assert not v_ok, "示範內容應低於視窗高度"
    app._enter_pan_mode()
    app.on_press(Ev(100, 100))
    for yy in (200, 350, 30):
        app.on_motion(Ev(100, yy))
    app.on_release(Ev(100, 30))
    app._on_wheel(Ev(delta=-120))
    assert app.wave_cv.yview()[0] == 0.0
    assert app.name_cv.yview()[0] == 0.0


def test_pan_scrolls_and_syncs_when_content_overflows(app):
    for i in range(30):
        app.model.add_signal(f"T{i}")
    app.render(); app.update_idletasks()
    assert app._scrollable()[1]
    app._enter_pan_mode()
    app.on_press(Ev(200, 400))
    app.on_motion(Ev(200, 100))
    wy, ny = app.wave_cv.yview()[0], app.name_cv.yview()[0]
    app.on_release(Ev(200, 100))
    assert wy > 0 and abs(wy - ny) < 1e-9
    # 超拖要被夾住且仍同步
    app.on_press(Ev(200, 500))
    app.on_motion(Ev(200, -5000))
    app.on_release(Ev(200, -5000))
    assert abs(app.wave_cv.yview()[0] - app.name_cv.yview()[0]) < 1e-9
    assert_invariants(app.model)


def test_render_snaps_back_when_content_shrinks(app):
    for i in range(30):
        app.model.add_signal(f"T{i}")
    app.render(); app.update_idletasks()
    app._enter_pan_mode()
    app.on_press(Ev(200, 400)); app.on_motion(Ev(200, 100)); app.on_release(Ev(200, 100))
    while len(app.model.signals) > 3:
        app.model.remove_signal(len(app.model.signals) - 1)
    app.render(); app.update_idletasks()
    assert app.wave_cv.yview()[0] == 0.0
    assert app.name_cv.yview()[0] == 0.0
    assert_invariants(app.model)


# ---------------------------------------------------------------- 複製貼上
def test_copy_paste_signals_fresh_sids(app):
    app.sig_sel = {0, 1}; app.selected = 1; app._copy_ctx = "signals"
    app.do_copy()
    before = {s["sid"] for s in app.model.signals}
    app.do_paste()
    assert len(app.model.signals) == 5
    new = [s for s in app.model.signals if s["sid"] not in before]
    assert len(new) == 2                            # 鐵則 2：複本配發新 sid
    names = [s["name"] for s in app.model.signals]
    assert len(names) == len(set(names))            # 名稱去重
    assert all(s["group"] is None for s in new)     # 複本預設不分組
    assert_invariants(app.model)


def test_copy_paste_cells_auto_adds_rows(app):
    app.cell_sel = (0, 2, 0, 3); app._copy_ctx = "cells"
    app.do_copy()
    app._hover = (2, 4)                             # 貼在 DATA 列 T4 -> 需要 3 列，自動加 2 列
    app.do_paste()
    assert len(app.model.signals) == 5
    assert app.model.signals[2]["cells"][4]["type"] == app.model.signals[0]["cells"][0]["type"]
    assert_invariants(app.model)


# ---------------------------------------------------------------- 範本插入
def test_insert_template_fresh_sids_and_group(app, tmp_path):
    blob = {"signals": [
        {"name": "CLK", "cells": [{"type": "CLK", "text": ""}] * 4},
        {"name": "MOSI", "cells": [{"type": "BUS", "text": "D0"}] * 4}]}
    p = tmp_path / "tpl.json"
    p.write_text(json.dumps(blob), encoding="utf-8")
    before = {s["sid"] for s in app.model.signals}
    app._insert_template({"name": "SPI", "path": str(p)})
    assert len(app.model.signals) == 5
    new = [s for s in app.model.signals if s["sid"] not in before]
    assert len(new) == 2 and all(s["sid"] not in before for s in new)
    gid = new[0]["group"]
    assert gid and app.model.groups[gid]["name"] == "SPI"   # 升為同名群組
    assert new[1]["cells"][0]["text"] == "D0"
    assert len(new[0]["cells"]) == app.model.n_periods       # 補齊週期
    names = [s["name"] for s in app.model.signals]
    assert len(names) == len(set(names))                     # 撞名自動改名
    assert_invariants(app.model)
