# -*- coding: utf-8 -*-
"""v1.36 run_mcp.py launcher tests (no `mcp` package required)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import run_mcp  # noqa: E402


def test_launch_invokes_server_main(monkeypatch):
    import retrowave.mcp_server as srv
    called = {}
    monkeypatch.setattr(srv, "main", lambda: called.setdefault("ran", True))
    run_mcp.launch()
    assert called.get("ran") is True


def test_missing_mcp_is_friendly(monkeypatch, capsys):
    import retrowave.mcp_server as srv

    def boom():
        raise ModuleNotFoundError("No module named 'mcp'", name="mcp")

    monkeypatch.setattr(srv, "main", boom)
    with pytest.raises(SystemExit) as ex:
        run_mcp.launch()
    assert ex.value.code == 1
    assert "pip install mcp" in capsys.readouterr().err


def test_other_import_errors_propagate(monkeypatch):
    import retrowave.mcp_server as srv

    def boom():
        raise ModuleNotFoundError("No module named 'numpy'", name="numpy")

    monkeypatch.setattr(srv, "main", boom)
    with pytest.raises(ModuleNotFoundError):
        run_mcp.launch()           # unrelated missing module must not be swallowed
