# -*- coding: utf-8 -*-
"""Drawing engine (drawing unit): a single drawing pipeline that draws to any duck-type Canvas
(on-screen tk.Canvas / PILCanvas / SVGCanvas), must not import tkinter. Design spec §4/§6/§7."""
import math

from .elements import (BusElement, ClkElement, HiZElement, HighElement,
                       LowElement, UnknownElement)
from .theme import Style


class Engine:
    def __init__(self):
        self.elements = {e.name: e for e in (
            HighElement(), LowElement(), HiZElement(),
            ClkElement(), BusElement(), UnknownElement())}
        self._wcol = Style.WAVE

    def elem(self, t):
        return self.elements.get(t)

    def meet(self, Lt, Rt, hi, mid, lo):
        eL = self.elements[Lt].exit_y(hi, mid, lo) if Lt in self.elements else None
        eR = self.elements[Rt].entry_y(hi, mid, lo) if Rt in self.elements else None
        if eL is not None and eR is not None:
            return eL if eL == eR else None
        if eL is not None: return eL
        if eR is not None: return eR
        return mid

    @staticmethod
    def same_data(a, b):
        return bool(a and b and a["type"] == b["type"]
                    and a["type"] in ("BUS", "Unknown")
                    and a.get("text", "") == b.get("text", ""))

    def draw(self, name_cv, wave_cv, model, sig_sel, geom, cell_sel=None):
        name_cv.delete("all"); wave_cv.delete("all")
        n = len(model.signals); npd = model.n_periods
        HH, RH, PW, NW = geom.header_h, geom.row_h, geom.period_w, geom.name_w
        rows = model.layout()
        total_h = HH + len(rows) * RH; grid_w = npd * PW
        max_off = max((s.get("offset", 0.0) for s in model.signals), default=0.0)
        wave_cv.configure(scrollregion=(0, 0, max(grid_w + max_off * PW, 10), max(total_h, 10)))
        name_cv.configure(scrollregion=(0, 0, NW, max(total_h, 10)))

        name_cv.create_rectangle(0, 0, NW, HH, fill=Style.FACE, outline=Style.FACE_DARK)
        name_cv.create_text(NW // 2, HH // 2, text="SIGNAL", font=Style.UI_FONT, fill=Style.TEXT)
        for p in range(npd):
            x = p * PW
            wave_cv.create_text(x + PW / 2, HH / 2, text=f"T{p}", font=Style.LABEL_FONT, fill=Style.TEXT)
            wave_cv.create_line(x, HH, x, total_h, fill=Style.DASH, dash=(2, 3))
        wave_cv.create_line(grid_w, HH, grid_w, total_h, fill=Style.DASH, dash=(2, 3))
        wave_cv.create_line(0, HH, grid_w, HH, fill=Style.GRID)

        sig_row = {}                       # signal index -> visible row (for cell_sel highlight)
        for r, row in enumerate(rows):
            kind, ref, depth, rgcol = row.kind, row.ref, row.depth, row.gcol
            row_top = HH + r * RH; row_bot = row_top + RH
            if kind == "group":            # ---- group header row (indented by depth) ----
                meta = model.groups.get(ref, {})
                gcol = rgcol
                gx = 8 + depth * 16
                gy = (row_top + row_bot) // 2
                col = gcol or Style.TEXT
                name_cv.create_rectangle(0, row_top, NW, row_bot, fill=Style.FACE, outline=Style.FACE_DARK)
                # Draw the collapse triangle as a vector polygon (not relying on font glyph
                # coverage for ▸/▾, so screen and PNG/SVG export stay consistent in any font environment)
                ts = 4 * self._scale_of(name_cv)
                if meta.get("collapsed"):       # pointing right (collapsed)
                    name_cv.create_polygon([gx, gy - ts, gx + ts * 1.6, gy, gx, gy + ts],
                                           fill=col, outline=col)
                else:                           # pointing down (expanded)
                    name_cv.create_polygon([gx - ts * 0.3, gy - ts * 0.7,
                                            gx + ts * 1.9, gy - ts * 0.7,
                                            gx + ts * 0.8, gy + ts * 0.9],
                                           fill=col, outline=col)
                name_cv.create_text(gx + 6 + ts * 1.9, gy, text=meta.get("name", ref),
                                    anchor="w", font=Style.NAME_FONT, fill=col)
                wave_cv.create_rectangle(0, row_top, grid_w, row_bot, fill=Style.FACE, outline="")
                if gcol:
                    wave_cv.create_rectangle(0, row_top, grid_w, row_top + 3, fill=gcol, outline="")
                wave_cv.create_line(0, row_bot, grid_w, row_bot, fill=Style.GRID)
                continue
            si = ref; sig = model.signals[si]; sig_row[si] = r    # ---- signal row ----
            hi, mid, lo = geom.levels(row_top)
            ox = sig.get("offset", 0.0) * PW
            gcol = rgcol                       # inherited from nearest ancestor group (already computed by layout)
            self._wcol = sig.get("color") or gcol or Style.WAVE   # custom color > group color > default
            namecol = sig.get("color") or gcol or Style.TEXT
            indent = 8 + depth * 16            # indent by nesting depth
            if si in sig_sel:
                name_cv.create_rectangle(0, row_top, NW, row_bot, fill=Style.SEL, outline="")
            name_cv.create_rectangle(0, row_top, NW, row_bot,
                                     fill="" if si in sig_sel else Style.CANVAS_BG, outline=Style.GRID)
            label = sig["name"] + (f"  Δ{sig['offset']:.2f}" if sig.get("offset") else "")
            name_cv.create_text(indent, (row_top + row_bot) // 2, text=label,
                                anchor="w", font=Style.NAME_FONT, fill=namecol)
            wave_cv.create_line(0, row_bot, grid_w, row_bot, fill=Style.GRID)
            cells = sig["cells"]
            for p in range(npd):
                pc = cells[p - 1] if p > 0 else None
                nc = cells[p + 1] if p < npd - 1 else None
                el = self.elem(cells[p]["type"])
                if el:
                    el.draw(self, wave_cv, geom, cells[p], pc, nc, p * PW + ox, hi, mid, lo)
            if ox > 0:                          # offset virtual extension (purely visual, not stored in data)
                f = self.elem(cells[0]["type"])
                if f is not None:
                    if f.kind == "DATA":        # BUS/Unknown: left-edge closing triangle (slope = BUS's swing/tw)
                        tw = geom.tw(); swing = lo - hi
                        half_w = abs(mid - hi) * tw / swing   # half-swing horizontal width = tw/2
                        base_x = ox - half_w    # closing start point (stepped back a half-swing along the BUS slope)
                        if base_x > 0:          # if there is room before the triangle, fill the parallel band
                            wave_cv.create_line(0, hi, base_x, hi, fill=self._wcol, width=2)
                            wave_cv.create_line(0, lo, base_x, lo, fill=self._wcol, width=2)
                            xh = xl = base_x; yh, yl = hi, lo
                        else:                   # step-back exceeds left edge -> clip at x=0 along the slope
                            t = (-base_x) / half_w  # fraction already traveled off-screen
                            xh = xl = 0.0
                            yh = hi + (mid - hi) * t
                            yl = lo + (mid - lo) * t
                        wave_cv.create_line(xh, yh, ox, mid, fill=self._wcol, width=2)
                        wave_cv.create_line(xl, yl, ox, mid, fill=self._wcol, width=2)
                    elif f.kind == "CLK":       # clock: fill the idle low level
                        wave_cv.create_line(0, lo, ox, lo, fill=self._wcol, width=2)
                    else:                       # single level: fill that level
                        y = f.entry_y(hi, mid, lo)
                        if y is not None:
                            wave_cv.create_line(0, y, ox, y, fill=self._wcol, width=2)
                wave_cv.create_rectangle(grid_w + 1, row_top, grid_w + ox + 2, row_bot,
                                         fill=Style.CANVAS_BG, outline="")   # trim the right end

        if cell_sel:
            s0, s1, p0, p1 = cell_sel
            for s in range(s0, s1 + 1):
                if s in sig_row:           # skip rows hidden by collapse
                    ox = model.signals[s].get("offset", 0.0) * PW
                    y0 = HH + sig_row[s] * RH; y1 = y0 + RH
                    wave_cv.create_rectangle(p0 * PW + ox, y0, (p1 + 1) * PW + ox, y1,
                                             fill=Style.MARQUEE_FILL, stipple="gray12",
                                             outline=Style.MARQUEE, dash=(3, 2), width=1)

        # ---- annotation layer: relation lines (below) + anchors (above) ----
        sid2idx = {s.get("sid"): i for i, s in enumerate(model.signals)}
        npos = self.node_positions(model, geom, sig_row, sid2idx)
        for ed in model.edges:
            a, b = npos.get(ed["frm"]), npos.get(ed["to"])
            if a and b:
                self.draw_edge(wave_cv, a, b, ed.get("label", ""), style=ed.get("style", "double"))
        for nid, xy in npos.items():
            self.draw_node(wave_cv, nid, xy)

    # ---- annotation drawing (shared by Engine and PILCanvas, consistent on export) ----
    @staticmethod
    def node_positions(model, geom, sig_row, sid2idx):
        HH, RH, PW = geom.header_h, geom.row_h, geom.period_w
        ex = {"start": 0.0, "mid": 0.5, "end": 1.0}
        pos = {}
        for nid, nd in model.nodes.items():
            si = sid2idx.get(nd.get("sid"))
            if si is None or si not in sig_row:
                continue
            ox = model.signals[si].get("offset", 0.0) * PW
            x = (nd["period"] + ex.get(nd.get("edge", "start"), 0.0)) * PW + ox
            y = HH + sig_row[si] * RH + RH / 2
            pos[nid] = (x, y)
        return pos

    ANNOT = "#6A3FB5"

    @staticmethod
    def _scale_of(cv):
        s = getattr(cv, "export_scale", 1)      # note: tkinter Canvas already has a scale() method, renamed to avoid collision
        return s if isinstance(s, (int, float)) else 1

    def draw_node(self, cv, nid, xy, hot=False):
        sc = self._scale_of(cv)
        x, y = xy; r = 4 * sc
        cv.create_oval(x - r, y - r, x + r, y + r,
                       fill=(Style.MARQUEE if hot else "#FFFFFF"), outline=self.ANNOT, width=2)
        cv.create_text(x, y - 10 * sc, text=nid, font=Style.LABEL_FONT, fill=self.ANNOT)

    def draw_edge(self, cv, a, b, label="", hot=False, style="double"):
        col = Style.MARQUEE if hot else self.ANNOT
        cv.create_line(a[0], a[1], b[0], b[1], fill=col, width=2)
        if style == "single":                   # single arrow: causal frm -> to
            self._arrow(cv, b, a, col)
        elif style == "measure":                # no arrow: measurement line (short ticks at both ends)
            self._tick(cv, a, b, col); self._tick(cv, b, a, col)
        else:                                   # double: double arrow (default)
            self._arrow(cv, b, a, col); self._arrow(cv, a, b, col)
        if label:
            cv.create_text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 8 * self._scale_of(cv),
                           text=label, font=Style.BUS_FONT, fill=col)

    @staticmethod
    def _arrow(cv, tip, frm, col):
        dx, dy = tip[0] - frm[0], tip[1] - frm[1]
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        sc = Engine._scale_of(cv)
        sz, hw = 11 * sc, 5 * sc                # arrow length / half-width (scaled by export factor)
        bx, by = tip[0] - ux * sz, tip[1] - uy * sz
        px, py = -uy, ux
        cv.create_polygon([tip[0], tip[1],
                           bx + px * hw, by + py * hw,
                           bx - px * hw, by - py * hw], fill=col, outline=col)

    @staticmethod
    def _tick(cv, end, other, col):             # vertical short tick at the measurement line endpoint
        dx, dy = other[0] - end[0], other[1] - end[1]
        L = math.hypot(dx, dy) or 1.0
        px, py = -dy / L, dx / L; t = 6 * Engine._scale_of(cv)
        cv.create_line(end[0] + px * t, end[1] + py * t,
                       end[0] - px * t, end[1] - py * t, fill=col, width=2)
