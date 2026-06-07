# -*- coding: utf-8 -*-
"""v1.23 export pipeline unit tests: pure functions (model, geom) -> file/dict, no window.
PNG tests auto-skip when Pillow is not installed."""
import json

import pytest

import retrowave
from retrowave.export import (export_png, export_svg, export_wavedrom,
                              svg_string, wavedrom_dict)


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
    assert set(d) == {"signal"}               # demo has no annotations -> no edge key
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
