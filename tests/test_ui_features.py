# -*- coding: utf-8 -*-
"""v1.41 UI features: cycle-column highlight (F1), experimental gesture mode (F2/F3)."""
import retrowave
import retrowave.usersettings as us
from conftest import Ev, cell_xy, assert_invariants


# ---------------------------------------------------------------- F1: cycle highlight
def _header_xy(app, period):
    g = app.geom
    return (period * g.period_w + g.period_w // 2, g.header_h // 2)


def test_header_click_toggles_cycle_highlight(app):
    assert app.hl_periods == set()
    x, y = _header_xy(app, 3)
    app.on_press(Ev(x, y))                       # click header T3
    assert app.hl_periods == {3}
    app.on_press(Ev(*_header_xy(app, 5)))
    assert app.hl_periods == {3, 5}              # multiple columns
    app.on_press(Ev(x, y))                       # click T3 again toggles off
    assert app.hl_periods == {5}
    app.update_idletasks()                        # renders without error


def test_header_click_does_not_paint(app):
    app._set_tool("H")
    before = app.model.signals[2]["cells"][3]["type"]
    app.on_press(Ev(*_header_xy(app, 3)))         # header click, not a cell
    assert app.model.signals[2]["cells"][3]["type"] == before
    assert app.hl_periods == {3}
    assert_invariants(app.model)


def test_highlight_is_view_only_not_in_document(app):
    app.hl_periods = {1, 2}
    assert "hl_periods" not in app.model.to_dict()       # not persisted to the document


# ---------------------------------------------------------------- F2: experimental toggle
def test_gesture_mode_toggle_persists(app, tmp_path, monkeypatch):
    monkeypatch.setattr(us, "SETTINGS_DIR", str(tmp_path))
    app._set_gesture_mode(True)
    assert app._gesture_mode is True and us.get_value("experimental_gesture") is True
    app._set_gesture_mode(False)
    assert app._gesture_mode is False and us.get_value("experimental_gesture") is False


# ---------------------------------------------------------------- F3: gesture mode
def test_gesture_tap_selects_cell_and_opens_palette(app):
    app._gesture_mode = True
    app._set_tool("H")                            # tool is irrelevant in gesture mode
    x, y = cell_xy(app, 2, 4)
    app.on_press(Ev(x, y)); app.on_release(Ev(x, y))   # quick tap = select, no paint
    assert app.cell_sel == (2, 2, 4, 4)
    assert app.model.signals[2]["cells"][4]["type"] != "H"   # tap did not paint
    assert app._palette is not None and app._palette.winfo_exists()
    app._close_palette()
    assert_invariants(app.model)


def test_gesture_palette_applies_element(app):
    app._gesture_mode = True
    app.on_press(Ev(*cell_xy(app, 2, 4))); app.on_release(Ev(*cell_xy(app, 2, 4)))
    app._apply_gesture_element("H")               # pick H from the floating palette
    assert app.model.signals[2]["cells"][4]["type"] == "H"
    assert app._palette is None                   # palette closed after applying
    assert app.doc.history()[0] >= 1              # one undo step (fill)
    assert_invariants(app.model)


def test_gesture_palette_delete_clears_to_low(app):
    app._gesture_mode = True
    app.doc.set_cell(2, 4, "BUS", "X")
    app.on_press(Ev(*cell_xy(app, 2, 4))); app.on_release(Ev(*cell_xy(app, 2, 4)))
    app._apply_gesture_element("__del__")
    assert app.model.signals[2]["cells"][4]["type"] == "L"
    assert_invariants(app.model)


def test_gesture_longpress_enters_pan(app):
    app._gesture_mode = True
    app.on_press(Ev(*cell_xy(app, 2, 4)))
    assert app._g_press is not None and not app._panning
    app._gesture_longpress()                      # fire the long-press timer directly
    assert app._panning is True and app._g_press is None
    app.on_release(Ev(*cell_xy(app, 2, 4)))
    assert app._panning is False


def test_gesture_drag_promotes_to_pan_not_paint(app):
    app._gesture_mode = True; app._set_tool("H")
    x, y = cell_xy(app, 2, 4)
    app.on_press(Ev(x, y))
    app.on_motion(Ev(x + 40, y))                  # movement -> pan, never paints
    assert app._panning is True
    app.on_release(Ev(x + 40, y))
    assert app.model.signals[2]["cells"][4]["type"] != "H"
    assert_invariants(app.model)
