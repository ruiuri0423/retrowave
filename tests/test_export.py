# -*- coding: utf-8 -*-
"""v1.23 export pipeline unit tests: pure functions (model, geom) -> file/dict, no window.
PNG tests auto-skip when Pillow is not installed."""
import json

import pytest

import retrowave
from retrowave.export import (export_png, export_svg, export_wavedrom,
                              import_wavedrom, read_wavedrom, svg_string,
                              wavedrom_dict, wavedrom_to_dict)
from conftest import assert_invariants


@pytest.fixture
def geom():
    return retrowave.Geometry()


# ---------------------------------------------------------------- SVG
def test_svg_string_structure_and_size(model, geom):
    s = svg_string(model, geom)
    assert s.startswith("<svg") and s.rstrip().endswith("</svg>")
    assert "<polyline" in s and "<text" in s and "<rect" in s
    assert "stroke-dasharray" in s            # per-period dashed gridlines preserved (README selling point)
    assert "A5" in s and "0x4" in s           # demo BUS data text
    rows = model.layout()
    W = geom.name_w + geom.period_w * model.n_periods
    H = geom.header_h + len(rows) * geom.row_h
    assert f'width="{W}"' in s and f'height="{H}"' in s


def test_export_svg_writes_file(model, geom, tmp_path):
    p = tmp_path / "out.svg"
    assert export_svg(model, geom, str(p)) == str(p)
    assert p.read_text(encoding="utf-8") == svg_string(model, geom)


def test_svg_offset_extends_width(model, geom):
    model.signals[0]["offset"] = 1.5
    s = svg_string(model, geom)
    W = geom.name_w + int(geom.period_w * model.n_periods + 1.5 * geom.period_w)
    assert f'width="{W}"' in s                # offset extends canvas width


# ---------------------------------------------------------------- WaveDrom
def test_wavedrom_demo_waves(model):
    d = wavedrom_dict(model)
    assert set(d) == {"signal", "config"}     # no annotations -> no edge; config carries hscale
    assert d["config"]["hscale"] >= 2         # widened so bus labels aren't cramped
    waves = {s["name"]: s for s in d["signal"]}
    assert waves["CLK"]["wave"] == "p" + "." * 11
    assert waves["RST_N"]["wave"] == "1" + "." * 11
    assert waves["DATA"]["wave"] == "0.=.=z=10..."   # repeated BUS values collapse to '.'
    assert waves["DATA"]["data"] == ["A5", "0F", "0x4"]
    assert "phase" not in waves["CLK"]


def test_wavedrom_groups_phase_nodes_edges(model):
    model.group_signals([1, 2], name="SPI")
    idx = {s["name"]: i for i, s in enumerate(model.signals)}
    model.signals[idx["DATA"]]["offset"] = 0.5
    a = model.add_node(model.signals[idx["RST_N"]]["sid"], 2, "start")
    b = model.add_node(model.signals[idx["DATA"]]["sid"], 5, "mid")
    model.add_edge(a, b, "t_su", "single")
    d = wavedrom_dict(model)
    groups = [x for x in d["signal"] if isinstance(x, list)]
    assert len(groups) == 1 and groups[0][0] == "SPI" and len(groups[0]) == 3   # nested array
    by = {}
    def collect(items):
        for it in items:
            if isinstance(it, list):
                collect(it[1:])
            elif isinstance(it, dict):
                by[it["name"]] = it
    collect(d["signal"])
    assert by["DATA"]["phase"] == -0.5         # WaveDrom phase is negated
    node = by["RST_N"]["node"]
    assert node[2] == a and set(node) <= {a, "."}
    assert d["edge"] == [f"{a}->{b} t_su"]     # single -> '->'


def test_export_wavedrom_writes_json(model, tmp_path):
    p = tmp_path / "w.json"
    export_wavedrom(model, str(p))
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d == wavedrom_dict(model)


# ---------------------------------------------------------------- WaveDrom import + round-trip
def _comparable(m):
    """Project a Model onto the subset WaveDrom preserves (drops gid/color and
    anchor edge-position), for round-trip equality checks."""
    by = {s["sid"]: s["name"] for s in m.signals}
    sigs = [(s["name"],
             tuple((c["type"], c.get("text", "")) for c in s["cells"]),
             round(s.get("offset", 0.0), 3)) for s in m.signals]

    def tree(nodes):
        out = []
        for nd in nodes:
            if nd.get("type") == "group":
                out.append((m.groups[nd["gid"]]["name"], tree(nd["children"])))
            else:
                out.append(by[nd["sid"]])
        return out

    anchors = sorted((by[nd["sid"]], nd["period"]) for nd in m.nodes.values())
    edges = sorted((by[m.nodes[e["frm"]]["sid"]], m.nodes[e["frm"]]["period"],
                    by[m.nodes[e["to"]]["sid"]], m.nodes[e["to"]]["period"],
                    e["style"], e.get("label", "")) for e in m.edges)
    return {"sigs": sigs, "tree": tree(m.group_tree),
            "n": m.n_periods, "anchors": anchors, "edges": edges}


def test_import_wavedrom_basic(check):
    wd = {"signal": [
        {"name": "CLK", "wave": "p......."},
        {"name": "DATA", "wave": "x.=..=x.", "data": ["A5", "0F"]},
        {"name": "RST", "wave": "01......"},
    ]}
    m = import_wavedrom(wd)
    assert [s["name"] for s in m.signals] == ["CLK", "DATA", "RST"]
    assert m.n_periods == 8
    assert m.signals[0]["cells"][0]["type"] == "CLK"
    assert [c["type"] for c in m.signals[0]["cells"]] == ["CLK"] * 8   # p then "." repeats
    d = m.signals[1]["cells"]
    assert d[0]["type"] == "Unknown"                                   # x
    assert (d[2]["type"], d[2]["text"]) == ("BUS", "A5")
    assert (d[3]["type"], d[3]["text"]) == ("BUS", "A5")              # "." keeps the value
    assert (d[5]["type"], d[5]["text"]) == ("BUS", "0F")              # next "=" -> next data
    assert m.signals[2]["cells"][0]["type"] == "L" and m.signals[2]["cells"][1]["type"] == "H"
    check(m)


def test_import_wavedrom_groups_phase_nodes_edges(check):
    wd = {"signal": [
        {"name": "CLK", "wave": "p..."},
        ["SPI",
         {"name": "CS", "wave": "10..", "node": ".a.."},
         {"name": "MOSI", "wave": "x=..", "data": ["CMD"], "phase": -0.5, "node": ".b.."}],
    ], "edge": ["a<->b t_su"]}
    m = import_wavedrom(wd)
    assert "SPI" in {g["name"] for g in m.groups.values()}
    mosi = next(s for s in m.signals if s["name"] == "MOSI")
    assert mosi["group"] is not None and round(mosi["offset"], 3) == 0.5   # phase negated
    assert len(m.nodes) == 2 and len(m.edges) == 1
    assert m.edges[0]["style"] == "double" and m.edges[0]["label"] == "t_su"
    check(m)


def test_wavedrom_roundtrip_model_to_wd_to_model(model, check):
    """Model -> wavedrom_dict -> import_wavedrom preserves the documented subset."""
    gid = model.group_signals([1, 2], name="SPI")
    model.groups[gid]["color"] = "#2266CC"           # not preserved (fine)
    idx = {s["name"]: i for i, s in enumerate(model.signals)}
    model.signals[idx["DATA"]]["offset"] = 0.25
    a = model.add_node(model.signals[idx["CLK"]]["sid"], 2, "start")
    b = model.add_node(model.signals[idx["DATA"]]["sid"], 4, "start")
    model.add_edge(a, b, "t_su", "single")
    m2 = import_wavedrom(wavedrom_dict(model))
    assert _comparable(m2) == _comparable(model)
    check(m2)


def test_wavedrom_import_idempotent(check):
    wd = {"signal": [
        {"name": "CLK", "wave": "p......."},
        ["BUS_GRP", {"name": "A", "wave": "x.=.=.x.", "data": ["1", "2"]}],
    ]}
    m1 = import_wavedrom(wd)
    m2 = import_wavedrom(wavedrom_dict(m1))          # second pass must equal first
    assert _comparable(m1) == _comparable(m2)
    check(m1); check(m2)


def test_import_wavedrom_data_boxes(check):
    """WaveDrom colored data boxes (2..9), not just '=', map to BUS and consume
    data[] in order (the test.json pattern that previously imported as Unknown)."""
    wd = {"signal": [
        {"name": "HCLK", "wave": "p......"},
        {"name": "HTRANS", "wave": "x344xxx", "data": ["NONSEQ", "SEQ", "SEQ"]},
        {"name": "HADDR", "wave": "x345xxx", "data": ["A1", "A2", "A3"], "node": ".abc..."},
    ], "edge": ["a~>b Pipeline"], "config": {"hscale": 1.5}}
    m = import_wavedrom(wd)
    tr = [(c["type"], c.get("text", "")) for c in
          next(s for s in m.signals if s["name"] == "HTRANS")["cells"]]
    assert tr[0] == ("Unknown", "")
    assert tr[1:4] == [("BUS", "NONSEQ"), ("BUS", "SEQ"), ("BUS", "SEQ")]   # 3,4,4 -> 3 boxes
    ad = [(c["type"], c.get("text", "")) for c in
          next(s for s in m.signals if s["name"] == "HADDR")["cells"]]
    assert ad[1:4] == [("BUS", "A1"), ("BUS", "A2"), ("BUS", "A3")]         # 3,4,5 distinct boxes
    assert len(m.nodes) == 3                                                # a,b,c anchors
    assert m.edges and m.edges[0]["style"] == "single"                     # ~> = causal/single
    check(m)


def test_import_wavedrom_clock_and_level_variants(check):
    wd = {"signal": [
        {"name": "nclk", "wave": "n..."},
        {"name": "lh", "wave": "lhLH"},
        {"name": "weak", "wave": "du.."},
        {"name": "gap", "wave": "1|0."},
    ]}
    m = import_wavedrom(wd)
    by = {s["name"]: [c["type"] for c in s["cells"]] for s in m.signals}
    assert by["nclk"][0] == "CLK"
    assert by["lh"] == ["L", "H", "L", "H"]
    assert by["weak"][0] == "L" and by["weak"][1] == "H"
    assert by["gap"] == ["H", "H", "L", "L"]      # '|' keeps the previous value / alignment
    check(m)


def test_wavedrom_export_hscale(model):
    assert wavedrom_dict(model)["config"]["hscale"] >= 2            # auto (demo labels <=4)
    assert "config" not in wavedrom_dict(model, hscale=1)           # explicit 1 disables
    assert wavedrom_dict(model, hscale=5)["config"]["hscale"] == 5  # explicit override
    model.set_cell(2, 0, "BUS", "VERYLONGLABEL")                    # long label -> wider
    assert wavedrom_dict(model)["config"]["hscale"] >= 4


def test_read_wavedrom_file(tmp_path, check):
    p = tmp_path / "w.json"
    p.write_text(json.dumps({"signal": [{"name": "X", "wave": "01."}]}), encoding="utf-8")
    m = read_wavedrom(str(p))
    assert [s["name"] for s in m.signals] == ["X"] and m.n_periods == 3
    check(m)


def test_wavedrom_to_dict_pads_unequal_waves(check):
    d = wavedrom_to_dict({"signal": [{"name": "long", "wave": "0123"},
                                     {"name": "short", "wave": "1"}]})
    assert d["n_periods"] == 4
    assert all(len(s["cells"]) == 4 for s in d["signals"])
    from retrowave import Model
    m = Model(); m.load_dict(d); check(m)


# ---------------------------------------------------------------- PNG
def test_png_dimensions_scale(model, geom, tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image
    p = tmp_path / "out.png"
    export_png(model, geom, str(p), scale=2)
    g = geom.copy_scaled(2)
    rows = model.layout()
    W = g.name_w + int(g.period_w * model.n_periods)
    H = g.header_h + len(rows) * g.row_h
    with Image.open(p) as img:
        assert img.size == (W, H)              # true high-resolution redraw (not upscaled)
