# -*- coding: utf-8 -*-
"""v1.27 onboarding tutorial tests: settings persistence, overlay flow (next/prev/finish checkbox/skip),
App integration (env-var suppression, forced reopen from Help)."""
import pytest

import retrowave.tutorial as tut
from retrowave.tutorial import TutorialOverlay


@pytest.fixture
def settings_tmp(tmp_path, monkeypatch):
    """Redirect the settings file to a temp dir, to avoid touching the real ~/.retrowave."""
    monkeypatch.setattr(tut, "SETTINGS_DIR", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------- settings persistence
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


# ---------------------------------------------------------------- overlay flow
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
    ov.next()                                     # pressing next on the last step doesn't overshoot
    assert ov.idx == n - 1
    ov.prev()
    assert ov.idx == n - 2
    ov.next()
    assert ov.dont_show.get() is True             # checked by default
    ov.finish()
    assert not ov.winfo_exists()
    assert tut.tutorial_enabled() is False        # "don't show" checked -> permanently disabled


def test_overlay_finish_unchecked_keeps_enabled(app, settings_tmp):
    ov = _open_overlay(app)
    ov.idx = len(ov.steps) - 1
    ov.dont_show.set(False)
    ov.finish()
    assert tut.tutorial_enabled() is True         # unchecked -> still shown next time


def test_overlay_skip_disables_permanently(app, settings_tmp):
    ov = _open_overlay(app)
    ov.skip()                                     # skip on the first step
    assert not ov.winfo_exists()
    assert tut.tutorial_enabled() is False


def test_overlay_highlights_have_targets(app, settings_tmp):
    """Step targets must be existing widgets (first and last steps are full-screen None)."""
    steps = app._tutorial_steps()
    assert steps[0][0] is None and steps[-1][0] is None
    for target, title, body in steps[1:-1]:
        assert target is not None and target.winfo_exists()
        assert title and body
    ov = _open_overlay(app)
    ov.idx = 1; ov._show_step()                   # a step with a target can draw a bbox
    assert ov._target_bbox(steps[1][0]) is not None
    ov.close()


# ---------------------------------------------------------------- App integration
def test_app_respects_env_suppression(app, settings_tmp):
    app._maybe_show_tutorial()                    # conftest already set RETROWAVE_NO_TUTORIAL
    assert getattr(app, "_tutorial", None) is None or not app._tutorial.winfo_exists()


def test_app_force_reopen_via_help(app, settings_tmp):
    tut.set_tutorial_enabled(False)               # even if the user has disabled it
    app._maybe_show_tutorial(force=True)          # the Help menu can still reopen it
    assert app._tutorial.winfo_exists()
    app._tutorial.skip()
