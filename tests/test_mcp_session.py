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
    r = s.render(format="svg")
    assert r["ok"] and r["svg"].startswith("<svg") and r["path"].endswith(".svg")


def test_render_png_when_pillow(s):
    pytest.importorskip("PIL")
    r = s.render(format="png", scale=1)
    assert r["ok"] and r["image_base64"] and r["path"].endswith(".png")


def test_render_unknown_format(s):
    assert s.render(format="bmp")["ok"] is False


def test_undo_redo(s):
    s.add_signal(name="Y")
    n = len(s.model.signals)
    assert s.undo()["undone"] is True and len(s.model.signals) == n - 1
    assert s.redo()["redone"] is True and len(s.model.signals) == n
    assert_invariants(s.model)


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
