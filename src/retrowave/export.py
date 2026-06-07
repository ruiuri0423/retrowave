# -*- coding: utf-8 -*-
"""匯出管線（繪圖單元）：純函式 (model, geom) → 檔案/dict，與 UI 完全無關、headless 可測。
PNG 需 Pillow（函式內延遲匯入）；SVG / WaveDrom 零依賴。
例外：EPS 匯出直接快照螢幕畫布（tk postscript），故留在 app（設計文件 §9.3）。"""
import json

from .backends import PILCanvas, SVGCanvas, _load_pil_fonts
from .engine import Engine
from .theme import Style


def export_png(model, geom, path, scale=2):
    """以 scale 倍幾何重新繪製輸出 PNG（真高解析重繪，非放大）。需 Pillow。"""
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
    Engine().draw(nd, wd, model, set(), g, None)   # 不含選取高亮
    final = Image.new("RGB", (NW + wave_w, total_h), Style.CANVAS_BG)
    final.paste(name_img, (0, 0)); final.paste(wave_img, (NW, 0))
    final.save(path)
    return path


def svg_string(model, geom):
    """組出整張圖的 SVG 字串（名稱欄 + 波形區合成單檔，虛線格線保留）。"""
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


def wavedrom_dict(model):
    """轉成 WaveDrom JSON 結構（交換格式；顏色/統一斜率視覺不保留，node/edge 可帶過去）。"""
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
            o["phase"] = -round(off, 3)     # WaveDrom phase 正值=左移，故取負
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
    return doc


def export_wavedrom(model, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wavedrom_dict(model), f, ensure_ascii=False, indent=2)
    return path
