# -*- coding: utf-8 -*-
"""v1.21 render coalescing: request_render() de-dupes within one event-loop cycle,
a synchronous render() cancels the pending request, and the final canvas/status bar matches the synchronous version."""
import pytest

from conftest import Ev, cell_xy, assert_invariants


@pytest.fixture
def draw_count(app, monkeypatch):
    """Count how many times Engine.draw actually runs (the core work of render)."""
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
    assert draw_count["n"] == 0                 # no redraw before idle
    app.update_idletasks()
    assert draw_count["n"] == 1                 # 10 requests -> 1 redraw
    app.update_idletasks()
    assert draw_count["n"] == 1                 # no leftover duplicate scheduling


def test_sync_render_cancels_pending_request(app, draw_count):
    app.request_render()
    app.render()                                # synchronous redraw
    assert draw_count["n"] == 1
    app.update_idletasks()
    assert draw_count["n"] == 1                 # pending request was cancelled, no second redraw


def test_request_after_sync_render_still_works(app, draw_count):
    app.render()
    app.request_render()
    app.update_idletasks()
    assert draw_count["n"] == 2


def test_paint_drag_burst_single_redraw_correct_result(app, draw_count):
    """One brush drag (press + 3 motion + release) coalesces into a single redraw, and all cells are painted."""
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
    """A deferred redraw must actually reach the canvas and status bar (equivalent to the synchronous version)."""
    app._enter_pan_mode()                       # internally goes through request_render
    app.update_idletasks()
    assert "Pan mode" in app.status.cget("text")
    app._set_tool("BUS")
    app.update_idletasks()
    assert "BUS" in app.status.cget("text")
    assert len(app.wave_cv.find_all()) > 0      # canvas has content


def test_render_pending_flag_cleared_after_idle(app):
    app.request_render()
    assert app._render_job is not None
    app.update_idletasks()
    assert app._render_job is None
