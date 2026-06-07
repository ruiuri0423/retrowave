# -*- coding: utf-8 -*-
"""Interaction smoke tests: real App + simulated mouse/keyboard events (briefly opens a window).
Covers: painting cells, brush row lock, BUS preservation, marquee select + fill, pan-mode panning, copy/paste, template insertion."""
import json

import retrowave
from conftest import Ev, cell_xy, assert_invariants


# ---------------------------------------------------------------- drawing
def test_click_paints_cell(app):
    app._set_tool("H")
    x, y = cell_xy(app, 2, 0)                       # DATA row T0 (originally L)
    app.on_press(Ev(x, y)); app.on_release(Ev(x, y))
    assert app.model.signals[2]["cells"][0]["type"] == "H"
    assert_invariants(app.model)


def test_drag_brush_locks_starting_row(app):
    app._set_tool("H")
    x0, y0 = cell_xy(app, 2, 1)
    x1, y1 = cell_xy(app, 0, 4)                     # drag up to another row, period 4
    app.on_press(Ev(x0, y0))
    app.on_motion(Ev(x1, y1))
    app.on_release(Ev(x1, y1))
    cells = app.model.signals[2]["cells"]
    assert [c["type"] for c in cells[1:5]] == ["H"] * 4   # only the starting row is painted
    assert app.model.signals[0]["cells"][4]["type"] == "CLK"  # other rows unaffected
    assert_invariants(app.model)


def test_bus_brush_preserves_existing_bus(app):
    app._set_tool("BUS")
    x0, y0 = cell_xy(app, 2, 1)                     # DATA: T2/T3=A5, T4=0F
    x1, y1 = cell_xy(app, 2, 4)
    app.on_press(Ev(x0, y0))
    app.on_motion(Ev(x1, y1))
    app.on_release(Ev(x1, y1))
    cells = app.model.signals[2]["cells"]
    assert cells[1]["type"] == "BUS"                # newly painted
    assert cells[2]["text"] == "A5" and cells[4]["text"] == "0F"  # existing BUS preserved
    assert_invariants(app.model)


def test_pan_mode_click_never_paints(app):
    app._enter_pan_mode()
    assert app.active_tool is None
    x, y = cell_xy(app, 2, 0)
    app.on_press(Ev(x, y)); app.on_release(Ev(x, y))
    assert app.model.signals[2]["cells"][0]["type"] == "L"
    assert_invariants(app.model)


# ---------------------------------------------------------------- marquee select + fill
def test_marquee_select_then_fill(app):
    x0, y0 = cell_xy(app, 1, 1)
    x1, y1 = cell_xy(app, 2, 3)
    app.on_press(Ev(x0, y0, state=retrowave.SHIFT_MASK))
    app.on_motion(Ev(x1, y1, state=retrowave.SHIFT_MASK))
    app.on_release(Ev(x1, y1, state=retrowave.SHIFT_MASK))
    assert app.cell_sel == (1, 2, 1, 3)
    app._set_tool("HiZ")                            # with a selection -> fill instead of switching tool
    for s in (1, 2):
        assert [c["type"] for c in app.model.signals[s]["cells"][1:4]] == ["HiZ"] * 3
    assert app.cell_sel is not None                 # selection kept after fill
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


# ---------------------------------------------------------------- pan-mode panning
def test_pan_locked_when_content_fits(app):
    h_ok, v_ok = app._scrollable()
    assert not v_ok, "demo content should be shorter than the window height"
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
    # over-dragging must be clamped and stay in sync
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


# ---------------------------------------------------------------- copy/paste
def test_copy_paste_signals_fresh_sids(app):
    app.sig_sel = {0, 1}; app.selected = 1; app._copy_ctx = "signals"
    app.do_copy()
    before = {s["sid"] for s in app.model.signals}
    app.do_paste()
    assert len(app.model.signals) == 5
    new = [s for s in app.model.signals if s["sid"] not in before]
    assert len(new) == 2                            # rule 2: copies get fresh sids
    names = [s["name"] for s in app.model.signals]
    assert len(names) == len(set(names))            # names de-duplicated
    assert all(s["group"] is None for s in new)     # copies default to ungrouped
    assert_invariants(app.model)


def test_copy_paste_cells_auto_adds_rows(app):
    app.cell_sel = (0, 2, 0, 3); app._copy_ctx = "cells"
    app.do_copy()
    app._hover = (2, 4)                             # paste at DATA row T4 -> needs 3 rows, auto-adds 2
    app.do_paste()
    assert len(app.model.signals) == 5
    assert app.model.signals[2]["cells"][4]["type"] == app.model.signals[0]["cells"][0]["type"]
    assert_invariants(app.model)


# ---------------------------------------------------------------- annotations / drag fix (v1.26)
def test_pan_mode_can_drag_annotation_edge(app, monkeypatch):
    """In pan mode, pressing on an anchor should draw an edge (anchor takes priority over panning)."""
    import retrowave.app as app_mod
    monkeypatch.setattr(app_mod.simpledialog, "askstring", lambda *a, **k: "t_x")
    a = app.doc.add_anchor(app.model.signals[0]["sid"], 2, "start")
    b = app.doc.add_anchor(app.model.signals[1]["sid"], 5, "start")
    app._enter_pan_mode()
    pos = app._node_screen_positions()
    ax, ay = map(int, pos[a]); bx, by = map(int, pos[b])
    app.on_press(Ev(ax, ay))
    assert app._connecting and not app._panning      # enters edge-drawing, not panning
    app.on_motion(Ev(bx, by))
    app.on_release(Ev(bx, by))
    assert len(app.model.edges) == 1
    e = app.model.edges[0]
    assert (e["frm"], e["to"], e["label"]) == (a, b, "t_x")
    assert_invariants(app.model)


def test_pan_mode_empty_press_still_pans(app):
    """In pan mode, pressing on a non-anchor spot still pans."""
    app._enter_pan_mode()
    app.on_press(Ev(200, 200))
    assert app._panning and not app._connecting
    app.on_release(Ev(200, 200))


def test_drag_signal_out_of_bottom_group(app):
    """When a group sits at the bottom (no top-level signal below it), dragging a member below all rows = move it out to the top-level tail."""
    gid = app.doc.group_signals([1, 2], name="G")
    rows = app.model.layout()                        # [CLK, G header, RST_N, DATA]
    assert rows[-1].kind == "sig"
    g = app.geom
    y_data = g.header_h + (len(rows) - 1) * g.row_h + g.row_h // 2
    y_below = g.header_h + (len(rows) + 1) * g.row_h
    app.on_name_press(Ev(10, y_data))
    app.on_name_drag(Ev(10, y_below))
    app.on_name_release(Ev(10, y_below))
    data = next(s for s in app.model.signals if s["name"] == "DATA")
    assert data["group"] is None                     # moved out of the group
    assert app.model.signals[-1]["name"] == "DATA"   # lands at the top-level tail
    assert gid in app.model.groups                   # group still exists (RST_N remains)
    assert_invariants(app.model)


def _row_y(app, row):
    g = app.geom
    return g.header_h + row * g.row_h + g.row_h // 2


def test_multi_select_drag_moves_block(app):
    """Selecting >1 signal and dragging moves the whole block (one undo step)."""
    for n in ("S3", "S4"):
        app.doc.add_signal(n)                        # CLK RST_N DATA S3 S4 (rows 0..4)
    app.sig_sel = {0, 2}; app.selected = 2; app._sig_anchor = 0   # CLK + DATA
    app.doc._undo.clear()
    rows = app.model.layout()
    app.on_name_press(Ev(10, _row_y(app, 2)))        # press on DATA (in selection)
    app.on_name_drag(Ev(10, _row_y(app, len(rows)) + app.geom.row_h))   # drag below all rows
    app.on_name_release(Ev(10, _row_y(app, len(rows)) + app.geom.row_h))
    names = [s["name"] for s in app.model.signals]
    assert names == ["RST_N", "S3", "S4", "CLK", "DATA"]   # block kept CLK->DATA order, moved to tail
    assert app.doc.history()[0] == 1                  # single undo step for the whole block
    sel_names = {app.model.signals[i]["name"] for i in app.sig_sel}
    assert sel_names == {"CLK", "DATA"}               # selection follows the moved signals
    assert_invariants(app.model)


def test_drag_row_outside_selection_moves_only_it(app):
    """Dragging a row that is NOT in the multi-selection moves just that one."""
    for n in ("S3", "S4"):
        app.doc.add_signal(n)
    app.sig_sel = {0, 1}; app.selected = 1           # CLK + RST_N selected
    rows = app.model.layout()
    app.on_name_press(Ev(10, _row_y(app, 4)))        # press on S4 (outside selection)
    app.on_name_drag(Ev(10, _row_y(app, 0) - app.geom.row_h))
    app.on_name_release(Ev(10, _row_y(app, 0) - app.geom.row_h))
    assert app.model.signals[0]["name"] == "S4"      # only S4 moved
    assert {app.model.signals[i]["name"] for i in app.sig_sel} == {"S4"}  # selection reset to it
    assert_invariants(app.model)


# ---------------------------------------------------------------- template insertion
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
    assert gid and app.model.groups[gid]["name"] == "SPI"   # promoted to a group of the same name
    assert new[1]["cells"][0]["text"] == "D0"
    assert len(new[0]["cells"]) == app.model.n_periods       # periods padded
    names = [s["name"] for s in app.model.signals]
    assert len(names) == len(set(names))                     # name clashes auto-renamed
    assert_invariants(app.model)
