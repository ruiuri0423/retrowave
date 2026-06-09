# -*- coding: utf-8 -*-
"""Export pipeline (drawing unit): pure functions (model, geom) -> file/dict,
fully UI-independent and headless-testable. PNG needs Pillow (lazily imported
inside the function); SVG / WaveDrom are zero-dependency.
Exception: EPS export snapshots the live screen canvas (tk postscript), so it
stays in the app shell (design spec §9.3)."""
import json

from .backends import PILCanvas, SVGCanvas, _load_pil_fonts
from .engine import Engine
from .theme import Style


def export_png(model, geom, path, scale=2):
    """Re-render at scale× geometry and write a PNG (true high-density re-render,
    not an upscale). Requires Pillow."""
    from PIL import Image, ImageDraw
    g = geom.copy_scaled(scale)
    fonts = _load_pil_fonts(scale)
    rows = model.layout()
    NW = g.name_w
    total_h = max(1, g.header_h + len(rows) * g.row_h)
    max_off = max((s.get("offset", 0.0) for s in model.signals), default=0.0)
    wave_w = max(1, int(g.period_w * model.n_periods + max_off * g.period_w))
    name_img = Image.new("RGB", (max(1, NW), total_h), Style.CANVAS_BG)
    wave_img = Image.new("RGB", (wave_w, total_h), Style.CANVAS_BG)
    nd = PILCanvas(ImageDraw.Draw(name_img), fonts, scale=scale)
    wd = PILCanvas(ImageDraw.Draw(wave_img), fonts, scale=scale)
    Engine().draw(nd, wd, model, set(), g, None)   # without selection highlight
    final = Image.new("RGB", (NW + wave_w, total_h), Style.CANVAS_BG)
    final.paste(name_img, (0, 0)); final.paste(wave_img, (NW, 0))
    final.save(path)
    return path


def svg_string(model, geom):
    """Build the full-diagram SVG string (name column + wave area composed into
    one file; the dashed period grid is preserved)."""
    g = geom; rows = model.layout()
    NW = g.name_w
    total_h = g.header_h + len(rows) * g.row_h
    max_off = max((s.get("offset", 0.0) for s in model.signals), default=0.0)
    wave_w = int(g.period_w * model.n_periods + max_off * g.period_w)
    W, H = NW + wave_w, total_h
    elems = []
    name_sc = SVGCanvas(elems, xoff=0)
    wave_sc = SVGCanvas(elems, xoff=NW)
    Engine().draw(name_sc, wave_sc, model, set(), g, None)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">\n'
            f'<rect x="0" y="0" width="{W}" height="{H}" fill="{Style.CANVAS_BG}"/>\n'
            + "\n".join(elems) + "\n</svg>\n")


def export_svg(model, geom, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg_string(model, geom))
    return path


def wavedrom_dict(model, hscale=None):
    """Convert to the WaveDrom JSON structure (interchange format; colors and the
    unified-slope styling are not preserved, node/edge annotations carry over).

    `hscale` widens the rendered cells so long bus labels (e.g. "NONSEQ") are not
    cramped in WaveDrom's narrow default cells. None = auto: scale up with the
    longest bus value; pass a number to force it, or 1 to disable."""
    m = model
    basech = {"CLK": "p", "H": "1", "L": "0", "HiZ": "z", "Unknown": "x", "BUS": "="}
    sid_nodes = {}                          # sid -> {period: nid}
    for nid, nd in m.nodes.items():
        sid_nodes.setdefault(nd["sid"], {})[nd["period"]] = nid

    def sig_obj(s):
        chars, data = [], []
        pt = ptxt = None
        for c in s["cells"]:
            t = c["type"]; txt = c.get("text", "")
            same = (pt == "BUS" and txt == ptxt) if t == "BUS" else (t == pt)
            if pt is not None and same:
                chars.append(".")
            else:
                ch = basech.get(t, "x"); chars.append(ch)
                if ch == "=":
                    data.append(txt)
            pt, ptxt = t, txt
        o = {"name": s["name"], "wave": "".join(chars)}
        if data:
            o["data"] = data
        off = s.get("offset", 0.0)
        if off:
            o["phase"] = -round(off, 3)     # positive WaveDrom phase shifts left, hence negated
        nm = sid_nodes.get(s.get("sid"))
        if nm:
            arr = ["."] * m.n_periods
            for p, nid in nm.items():
                if 0 <= p < m.n_periods:
                    arr[p] = nid
            o["node"] = "".join(arr)
        return o

    by_sid = {s["sid"]: s for s in m.signals}

    def walk(nodes):
        out = []
        for nd in nodes:
            if nd.get("type") == "group":
                grp = [nd.get("name", nd.get("gid", ""))]
                grp += walk(nd.get("children", []))
                out.append(grp)
            else:
                s = by_sid.get(nd.get("sid"))
                if s is not None:
                    out.append(sig_obj(s))
        return out

    doc = {"signal": walk(m.group_tree)}
    if m.edges:
        op = {"double": "<->", "single": "->", "measure": "-"}
        ed = []
        for e in m.edges:
            if e["frm"] in m.nodes and e["to"] in m.nodes:
                line = f'{e["frm"]}{op.get(e.get("style", "double"), "<->")}{e["to"]}'
                if e.get("label"):
                    line += f' {e["label"]}'
                ed.append(line)
        if ed:
            doc["edge"] = ed
    if hscale is None:                          # auto: widen for the longest bus label
        longest = max((len(c.get("text", "")) for s in m.signals for c in s["cells"]
                       if c["type"] == "BUS"), default=0)
        hscale = 2 if longest <= 4 else 3 if longest <= 8 else 4
    if hscale and hscale != 1:
        doc["config"] = {"hscale": hscale}
    return doc


def export_wavedrom(model, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wavedrom_dict(model), f, ensure_ascii=False, indent=2)
    return path


# ---- WaveDrom import (inverse of wavedrom_dict) ----------------------------
# Accepts the broad WaveDrom wave vocabulary, not just what our export emits.
# Not preserved on a round-trip (documented): per-signal/group colors, the
# unified-slope styling, group ids (names survive), and anchor edge-position
# (the `node` string encodes only the period, so anchors re-import as "start").
#
# Clock/level variants collapse to our element set; the colored data boxes
# (= and 2..9) all become BUS and each consumes the next `data[]` entry.
_WD_REV = {
    "p": "CLK", "P": "CLK", "n": "CLK", "N": "CLK",   # clock variants
    "1": "H", "h": "H", "H": "H", "u": "H",           # high / weak pull-up
    "0": "L", "l": "L", "L": "L", "d": "L",           # low / weak pull-down
    "z": "HiZ", "x": "Unknown",
}
_WD_DATA = set("=23456789")                            # data boxes -> BUS, consume data[]


def _wd_edge_style(op):
    """WaveDrom edge op -> our style. <…> = double; …> = single (causal);
    otherwise a plain measurement line."""
    if "<" in op and ">" in op:
        return "double"
    if ">" in op:
        return "single"
    return "measure"


def _wd_parse_edge(line):
    import re
    m = re.match(r"\s*([0-9A-Za-z]+)\s*([<>~|+*-]+)\s*([0-9A-Za-z]+)\s*(.*)", line)
    if not m:
        return None
    frm, op, to, label = m.group(1), m.group(2), m.group(3), m.group(4).strip()
    return {"frm": frm, "to": to, "label": label, "style": _wd_edge_style(op)}


def wavedrom_to_dict(data):
    """Parse a WaveDrom JSON object into a RetroWave document dict (the shape
    Model.load_dict consumes). Pure data transform; see notes above for the
    preserved subset."""
    signals, nodes, edges = [], {}, {}
    seq = {"sid": 0, "gid": 0, "np": 1}

    def parse_signal(obj):
        seq["sid"] += 1
        sid = seq["sid"]
        wave = obj.get("wave", "") or ""
        data_iter = iter(obj.get("data", []) or [])
        cells = []
        pt, ptx = "L", ""                       # a leading "." (rare) becomes L
        for ch in wave:
            if ch in ".|":                      # "." continue; "|" gap -> keep alignment
                cells.append({"type": pt, "text": ptx})
            elif ch in _WD_DATA:                # data box -> BUS, consume next data[]
                ptx = next(data_iter, ""); pt = "BUS"
                cells.append({"type": "BUS", "text": ptx})
            else:
                pt = _WD_REV.get(ch, "Unknown"); ptx = ""
                cells.append({"type": pt, "text": ptx})
        seq["np"] = max(seq["np"], len(cells))
        phase = obj.get("phase")
        signals.append({"name": obj.get("name", "SIG"),
                        "offset": -float(phase) if phase else 0.0,
                        "color": None, "group": None, "sid": sid, "cells": cells})
        for p, c in enumerate(obj.get("node", "") or ""):
            if c != ".":
                nodes[c] = {"sid": sid, "period": p, "edge": "start"}
        return {"type": "sig", "sid": sid}

    def build(items):
        out = []
        for it in items:
            if isinstance(it, list):            # ["name", child, child, ...] -> group
                name = it[0] if it and isinstance(it[0], str) else "Group"
                children = build(it[1:])
                if children:
                    seq["gid"] += 1
                    out.append({"type": "group", "gid": f"g{seq['gid']}", "name": name,
                                "collapsed": False, "color": None, "children": children})
            elif isinstance(it, dict) and ("wave" in it or "name" in it):
                out.append(parse_signal(it))
            # bare {} spacers / config strings are skipped
        return out

    group_tree = build(data.get("signal", []) if isinstance(data, dict) else [])
    NP = seq["np"]
    for s in signals:                           # pad short rows to the longest wave
        s["cells"] += [{"type": "L", "text": ""} for _ in range(NP - len(s["cells"]))]
    for line in (data.get("edge", []) if isinstance(data, dict) else []):
        e = _wd_parse_edge(line)
        if e and e["frm"] in nodes and e["to"] in nodes:
            edges[len(edges)] = e
    return {"version": "2.0", "n_periods": NP, "signals": signals,
            "group_tree": group_tree, "nodes": nodes, "edges": list(edges.values())}


def import_wavedrom(data):
    """WaveDrom JSON object -> a validated Model (runs load_dict, which enforces
    the §2.6 invariants and prunes orphan annotations)."""
    from .model import Model
    m = Model()
    m.load_dict(wavedrom_to_dict(data))
    return m


def read_wavedrom(path):
    with open(path, encoding="utf-8") as f:
        return import_wavedrom(json.load(f))
