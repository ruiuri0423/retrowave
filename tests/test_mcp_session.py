# -*- coding: utf-8 -*-
"""v1.35 MCP command-injection session tests (headless; the `mcp` package is NOT
required — only WaveSession, which is pure Python over Document)."""
import json

import pytest

from retrowave.mcp_server import WaveSession
from conftest import assert_invariants


@pytest.fixture
def s():
    return WaveSession()


def test_build_via_commands_only(s):
    """The model authors purely through commands — no JSON hand-writing."""
    s.new_document()
    # start from a clean 3-signal demo; add a fourth and paint it
    idx = s.add_signal(name="CLK", fill="CLK")["index"]
    assert s.fill(idx, 0, s.model.n_periods - 1, "CLK")["filled"] == s.model.n_periods
    assert all(c["type"] == "CLK" for c in s.model.signals[idx]["cells"])
    assert_invariants(s.model)


def test_get_document_shapes(s):
    d = s.get_document()
    assert d["ok"] and "compact" in d and "signals" in d
    assert d["signals"][0]["index"] == 0
    full = s.get_document(full=True)
    assert "document" in full and "signals" in full["document"]


def test_fill_is_single_undo_step(s):
    s.add_signal(name="X", fill="L")
    i = len(s.model.signals) - 1
    s.doc._undo.clear()
    s.fill(i, 0, 5, "H")
    assert s.doc.history()[0] == 1            # one undo unit for the whole fill
    s.undo()
    assert all(c["type"] == "L" for c in s.model.signals[i]["cells"])
    assert_invariants(s.model)


def test_add_signals_batch_one_undo(s):
    """Many signals (named/auto, custom fill) land in one undo step."""
    s.doc._undo.clear()
    n0 = len(s.model.signals)
    r = s.add_signals(signals=[{"name": "SCL", "fill": "H"}, {"name": "SDA"}, {}])
    assert r["ok"] and len(r["added"]) == 3
    assert [a["name"] for a in r["added"]][:2] == ["SCL", "SDA"]
    assert len(s.model.signals) == n0 + 3
    assert s.model.signals[r["added"][0]["index"]]["cells"][0]["type"] == "H"
    assert s.doc.history()[0] == 1            # one undo unit for the whole batch
    s.undo()
    assert len(s.model.signals) == n0
    assert_invariants(s.model)


def test_add_signals_atomic_on_bad_entry(s):
    """A bad fill rejects the whole batch — nothing added, no undo step."""
    s.doc._undo.clear()
    n0 = len(s.model.signals)
    r = s.add_signals(signals=[{"name": "OK"}, {"fill": "NOPE"}])
    assert r["ok"] is False and len(s.model.signals) == n0
    assert s.doc.history()[0] == 0
    assert_invariants(s.model)


def test_singular_tools_removed_from_tool_list():
    """v1.47: plural-only surface — a single item is a one-element list."""
    from retrowave import mcp_server
    assert "set_cell" not in mcp_server._TOOLS and "add_signal" not in mcp_server._TOOLS
    assert "set_cells" in mcp_server._TOOLS and "add_signals" in mcp_server._TOOLS


def test_set_cells_batch_one_undo(s):
    """Many cells with distinct values land in a single undo step."""
    s.doc._undo.clear()
    r = s.set_cells(cells=[
        {"signal": 0, "period": 0, "type": "BUS", "text": "D0"},
        {"signal": 0, "period": 1, "type": "BUS", "text": "D1"},
        {"signal": 1, "period": 0, "type": "H"},
    ])
    assert r["ok"] and r["set"] == 3
    assert s.model.signals[0]["cells"][0]["type"] == "BUS"
    assert s.model.signals[0]["cells"][0]["text"] == "D0"
    assert s.model.signals[1]["cells"][0]["type"] == "H"
    assert s.doc.history()[0] == 1            # exactly one undo unit for the whole batch
    s.undo()
    assert s.model.signals[0]["cells"][0]["text"] == ""   # whole batch reverted at once
    assert_invariants(s.model)


def test_set_cells_atomic_on_bad_entry(s):
    """A malformed entry changes nothing and pushes no undo step."""
    s.doc._undo.clear()
    base = s.model.signals[0]["cells"][0]["type"]
    r = s.set_cells(cells=[
        {"signal": 0, "period": 0, "type": "BUS", "text": "x"},
        {"signal": 0, "period": 1, "type": "NOPE"},      # invalid type -> whole batch rejected
    ])
    assert r["ok"] is False
    assert s.model.signals[0]["cells"][0]["type"] == base   # nothing written
    assert s.doc.history()[0] == 0                          # no undo step
    # out-of-range index is likewise rejected atomically
    assert s.set_cells(cells=[{"signal": 99, "period": 0, "type": "H"}])["ok"] is False
    assert_invariants(s.model)


def test_set_periods(s):
    """Regression: set_periods must call Document.set_n_periods (name bug)."""
    r = s.set_periods(8)
    assert r["ok"] and r["n_periods"] == 8 and s.model.n_periods == 8
    assert all(len(sig["cells"]) == 8 for sig in s.model.signals)
    assert_invariants(s.model)


def test_set_cell_validation(s):
    assert s.set_cell(0, 0, "BogusType")["ok"] is False
    assert s.set_cell(99, 0, "H")["set"] is False          # out of range -> False (no event)
    assert s.set_cell(0, 0, "H")["set"] is True
    assert_invariants(s.model)


def test_groups_and_annotations_via_commands(s):
    g = s.create_group([1, 2], name="SPI")
    gid = g["gid"]
    assert gid in s.model.groups
    a = s.add_anchor(0, 2, "start")["nid"]
    b = s.add_anchor(1, 4, "start")["nid"]
    assert s.add_edge(a, a)["ok"] is False                 # self-loop rejected
    assert s.add_edge(a, b, "t_su", "single")["ok"] is True
    assert s.toggle_collapse(gid)["collapsed"] is True
    assert s.dissolve_group(gid)["dissolved"] is True
    assert gid not in s.model.groups
    assert_invariants(s.model)


def test_open_document_existing_file_only(s, tmp_path):
    # save current doc to a real file, mutate, then open it back
    p = tmp_path / "saved.json"
    p.write_text(json.dumps(s.model.to_dict()), encoding="utf-8")
    s.add_signal(name="EXTRA")
    assert len(s.model.signals) == 4
    r = s.open_document(str(p))
    assert r["ok"] and len(s.model.signals) == 3           # back to the saved state
    assert s.open_document(str(tmp_path / "nope.json"))["ok"] is False
    assert_invariants(s.model)


def test_import_wavedrom_file(s, tmp_path):
    p = tmp_path / "w.json"
    p.write_text(json.dumps({"signal": [{"name": "A", "wave": "01.="}]}), encoding="utf-8")
    r = s.import_wavedrom(str(p))
    assert r["ok"] and [x["name"] for x in s.model.signals] == ["A"]
    assert_invariants(s.model)


def test_render_svg_no_pillow_needed(s):
    import os
    r = s.render(format="svg")
    assert r["ok"] and r["path"].endswith(".svg") and r["bytes"] > 0
    assert os.path.exists(r["path"])             # bytes returned, not inlined markup
    assert open(r["path"], encoding="utf-8").read().startswith("<svg")


def test_render_png_when_pillow(s):
    import os
    pytest.importorskip("PIL")
    r = s.render(format="png", scale=1)                # inline defaults to False
    assert r["ok"] and r["path"].endswith(".png") and r["bytes"] > 0
    assert os.path.exists(r["path"]) and "image_base64" not in r   # no giant blob


def test_render_inline_returns_image_block(s):
    pytest.importorskip("PIL")
    pytest.importorskip("mcp")
    from mcp.server.fastmcp import Image
    r = s.render(format="png", scale=1, inline=True)
    assert isinstance(r, Image)                        # MCP image content block, not a dict


def test_render_inline_falls_back_without_mcp(s, monkeypatch):
    """inline=True is safe even if `mcp` is absent: it degrades to the path result."""
    pytest.importorskip("PIL")
    import builtins
    real_import = builtins.__import__

    def no_mcp(name, *a, **k):
        if name.startswith("mcp"):
            raise ImportError("mcp not installed")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_mcp)
    r = s.render(format="png", scale=1, inline=True)
    assert r["ok"] and r["path"].endswith(".png") and "inline_unavailable" in r


def test_render_unknown_format(s):
    assert s.render(format="bmp")["ok"] is False


def test_undo_redo(s):
    s.add_signal(name="Y")
    n = len(s.model.signals)
    assert s.undo()["undone"] is True and len(s.model.signals) == n - 1
    assert s.redo()["redone"] is True and len(s.model.signals) == n
    assert_invariants(s.model)


def test_help_returns_guide(s):
    r = s.help()
    assert r["ok"] and "command" in r["guide"].lower()
    assert "add_signal" in r["guide"] and "waveform://schema" in r["guide"]
    from retrowave import mcp_server
    assert "help" in mcp_server._TOOLS          # surfaced as a tool, not just a resource


def test_tool_list_matches_methods():
    """Every advertised tool name is a real WaveSession method (no typos)."""
    from retrowave import mcp_server
    for name in mcp_server._TOOLS:
        assert callable(getattr(WaveSession, name, None)), f"missing tool method: {name}"


def test_fastmcp_server_builds():
    """The stdio wiring registers every tool + resource without error (requires
    the `mcp` package; skipped otherwise). Regression guard for the FastMCP
    resource-decorator signature bug fixed in v1.37."""
    pytest.importorskip("mcp")
    import asyncio
    from retrowave.mcp_server import build_server, _TOOLS, _RESOURCES
    srv = build_server()
    tools = asyncio.run(srv.list_tools())
    resources = asyncio.run(srv.list_resources())
    assert {t.name for t in tools} == set(_TOOLS)
    assert {str(r.uri) for r in resources} == set(_RESOURCES)
    # Regression: type annotations must yield integer/array schemas (not string),
    # otherwise int comparisons inside Document fail at call time.
    by = {t.name: t.inputSchema["properties"] for t in tools}
    assert by["fill"]["signal"]["type"] == "integer"
    assert by["fill"]["start"]["type"] == "integer"
    assert by["set_cells"]["cells"]["type"] == "array"
    assert by["add_signals"]["signals"]["type"] == "array"
    assert by["remove_signals"]["indices"]["type"] == "array"
    assert by["create_group"]["indices"]["type"] == "array"
    assert by["set_offset"]["value"]["type"] == "number"
    assert by["get_document"]["full"]["type"] == "boolean"
