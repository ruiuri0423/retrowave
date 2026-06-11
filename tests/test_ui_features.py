# -*- coding: utf-8 -*-
"""v1.41 UI features: cycle-column highlight (F1), experimental gesture mode (F2/F3)."""
import retrowave
import retrowave.usersettings as us
from conftest import Ev, cell_xy, assert_invariants


# ---------------------------------------------------------------- F1: cycle highlight
def _header_xy(app, period):
    g = app.geom
    return (period * g.period_w + g.period_w // 2, g.header_h // 2)


def test_header_click_single_vs_multi(app):
    assert app.hl_periods == set()
    app.on_press(Ev(*_header_xy(app, 3)))                 # plain click = single
    assert app.hl_periods == {3}
    app.on_press(Ev(*_header_xy(app, 5)))                 # plain click elsewhere = replace
    assert app.hl_periods == {5}
    app.on_press(Ev(*_header_xy(app, 8), state=retrowave.SHIFT_MASK))   # Shift = range from anchor(5)..8
    assert app.hl_periods == {5, 6, 7, 8}
    app.on_press(Ev(*_header_xy(app, 2), state=retrowave.CTRL_MASK))    # Ctrl = add single
    assert app.hl_periods == {2, 5, 6, 7, 8}
    app.on_press(Ev(*_header_xy(app, 2), state=retrowave.CTRL_MASK))    # Ctrl again = toggle off
    assert app.hl_periods == {5, 6, 7, 8}
    app.on_press(Ev(*_header_xy(app, 3)))                 # plain click = single (replace)
    assert app.hl_periods == {3}
    app.on_press(Ev(*_header_xy(app, 3)))                 # same again = clear
    assert app.hl_periods == set()
    app.update_idletasks()


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


def test_gesture_longpress_cursor_restored_on_release(app):
    """Long-press shows the pan cursor (fleur); releasing must restore the
    gesture-mode hand cursor (was lingering as fleur)."""
    app._gesture_mode = True
    app.wave_cv.configure(cursor="hand2")
    app.on_press(Ev(*cell_xy(app, 2, 4)))
    app._gesture_longpress()
    assert str(app.wave_cv.cget("cursor")) == "fleur"     # pan affordance while held
    app.on_release(Ev(*cell_xy(app, 2, 4)))
    assert str(app.wave_cv.cget("cursor")) == "hand2"     # back to tap-to-select


def test_pan_mode_cursor_stays_fleur_after_pan(app):
    """Outside gesture mode, Esc pan mode keeps the fleur cursor across drags
    (still in pan mode until a tool is picked)."""
    app._enter_pan_mode()
    assert str(app.wave_cv.cget("cursor")) == "fleur"
    x, y = cell_xy(app, 2, 4)
    app.on_press(Ev(x, y)); app.on_motion(Ev(x + 30, y)); app.on_release(Ev(x + 30, y))
    assert str(app.wave_cv.cget("cursor")) == "fleur"


def test_gesture_drag_promotes_to_pan_not_paint(app):
    app._gesture_mode = True; app._set_tool("H")
    x, y = cell_xy(app, 2, 4)
    app.on_press(Ev(x, y))
    app.on_motion(Ev(x + 40, y))                  # movement -> pan, never paints
    assert app._panning is True
    app.on_release(Ev(x + 40, y))
    assert app.model.signals[2]["cells"][4]["type"] != "H"
    assert_invariants(app.model)


def test_esc_in_gesture_mode_stays_gesture(app):
    """Esc clears selection/palette but must NOT switch gesture mode to pan."""
    app._gesture_mode = True
    app.on_press(Ev(*cell_xy(app, 2, 4))); app.on_release(Ev(*cell_xy(app, 2, 4)))
    assert app._palette is not None
    app._enter_pan_mode()                         # Esc
    assert app._gesture_mode is True              # still gesture, not pan
    assert app.active_tool is not None            # tool not nulled (that's pan-mode behavior)
    assert app._palette is None and app.cell_sel is None


def test_gesture_box_select_resets_state_after_palette(app):
    """After a Shift-drag box-select pops the palette, drag/select state is cleared
    so a stray release leaking through the closed palette can't start a new box."""
    app._gesture_mode = True
    x0, y0 = cell_xy(app, 1, 1); x1, y1 = cell_xy(app, 2, 3)
    app.on_press(Ev(x0, y0, state=retrowave.SHIFT_MASK))
    app.on_motion(Ev(x1, y1, state=retrowave.SHIFT_MASK))
    app.on_release(Ev(x1, y1, state=retrowave.SHIFT_MASK))
    assert app.cell_sel == (1, 2, 1, 3) and app._palette is not None
    assert app._selecting is False and app._press is None     # state reset
    # apply an element, then a stray release on the canvas must NOT create a box
    app._apply_gesture_element("HiZ")
    before = app.cell_sel
    app.on_release(Ev(x1, y1))                     # leaked release, clean state
    assert app.cell_sel == before                  # no spurious re-box
    assert_invariants(app.model)
